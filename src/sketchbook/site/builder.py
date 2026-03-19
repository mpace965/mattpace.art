"""Static site builder.

Discovers SiteOutput nodes in each sketch, iterates saved presets, bakes
variant images, and renders feed and sketch pages into dist/.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from sketchbook.core.executor import execute
from sketchbook.core.sketch import Sketch
from sketchbook.steps.site_output import SiteOutput

log = logging.getLogger("sketchbook.site.builder")

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _slug(sketch_id: str) -> str:
    """Convert a sketch ID (snake_case) to a URL slug (kebab-case)."""
    return sketch_id.replace("_", "-")


def build_site(
    sketch_classes: dict[str, type[Sketch]],
    sketches_dir: Path,
    dist_dir: Path,
) -> None:
    """Build the static site from all sketches that have SiteOutput nodes and saved presets.

    For each qualifying sketch, iterates saved presets, executes the full pipeline,
    and copies the SiteOutput node's image to dist/<slug>/variants/<preset>.png.
    Renders feed and individual sketch pages using Jinja2 templates.
    """
    dist_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)
    feed_tmpl = env.get_template("feed.html")
    sketch_tmpl = env.get_template("sketch_page.html")

    entries: list[dict[str, Any]] = []

    for sketch_id, sketch_cls in sketch_classes.items():
        sketch_dir = sketches_dir / sketch_id
        log.info(f"Processing sketch '{sketch_id}'")

        sketch = sketch_cls(sketch_dir)

        site_nodes = [n for n in sketch.dag.topo_sort() if isinstance(n.step, SiteOutput)]
        if not site_nodes:
            log.info(f"Skipping '{sketch_id}': no SiteOutput node")
            continue

        all_presets = sketch.preset_manager.list_presets()
        if not all_presets:
            log.info(f"Skipping '{sketch_id}': no saved presets")
            continue

        if sketch.site_presets is not None:
            presets = [p for p in sketch.site_presets if p in all_presets]
            missing = [p for p in sketch.site_presets if p not in all_presets]
            if missing:
                log.warning(f"  site_presets references unknown preset(s): {missing}")
        else:
            presets = all_presets

        if not presets:
            log.info(f"Skipping '{sketch_id}': no matching presets after filtering")
            continue

        slug = _slug(sketch_id)
        sketch_dist = dist_dir / slug
        variants_dir = sketch_dist / "variants"
        variants_dir.mkdir(parents=True, exist_ok=True)

        produced: list[str] = []
        for preset_name in presets:
            sketch.preset_manager.load_preset(preset_name, sketch.dag)
            result = execute(sketch.dag)
            if not result.ok:
                log.warning(f"  preset '{preset_name}' failed: {result.errors}")
                continue

            for site_node in site_nodes:
                if site_node.output is not None:
                    dest = variants_dir / f"{preset_name}.png"
                    site_node.output.save(dest)
                    log.info(f"  baked {preset_name} -> {dest}")

            produced.append(preset_name)

        if not produced:
            log.warning(f"Skipping '{sketch_id}': all presets failed")
            shutil.rmtree(sketch_dist)
            continue

        sketch_html = sketch_tmpl.render(
            name=sketch.name,
            description=sketch.description,
            date=sketch.date,
            slug=slug,
            variants=produced,
        )
        (sketch_dist / "index.html").write_text(sketch_html)

        entries.append({
            "slug": slug,
            "name": sketch.name,
            "description": sketch.description,
            "date": sketch.date,
            "variants": produced,
        })
        log.info(f"Built '{sketch_id}' with {len(produced)} variant(s)")

    feed_html = feed_tmpl.render(entries=entries)
    (dist_dir / "index.html").write_text(feed_html)
    log.info(f"Built feed with {len(entries)} sketch(es) -> {dist_dir / 'index.html'}")
