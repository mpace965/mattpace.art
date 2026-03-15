"""CLI dispatcher for analysis pipelines."""

import argparse
import importlib
import sys
from pathlib import Path

PIPELINES_DIR = Path(__file__).parent / "pipelines"


def discover_pipelines() -> dict[str, object]:
    pipelines = {}
    for path in sorted(PIPELINES_DIR.glob("*/pipeline.py")):
        name = path.parent.name
        module = importlib.import_module(f"pipelines.{name}.pipeline")
        pipelines[name] = module
    return pipelines


def cmd_run(args: argparse.Namespace) -> None:
    pipelines = discover_pipelines()
    if args.pipeline not in pipelines:
        print(f"error: unknown pipeline '{args.pipeline}'", file=sys.stderr)
        print(f"available: {', '.join(pipelines)}", file=sys.stderr)
        sys.exit(1)
    module = pipelines[args.pipeline]
    module.run(args.sketch, image_stem=args.image)


def cmd_list_sketches(_args: argparse.Namespace) -> None:
    from sketchbook.paths import list_sketches
    for name in list_sketches():
        print(name)


def cmd_list_pipelines(_args: argparse.Namespace) -> None:
    for name in discover_pipelines():
        print(name)


def main() -> None:
    parser = argparse.ArgumentParser(description="analyze sketch assets")
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="run a pipeline against a sketch")
    run_p.add_argument("pipeline", help="pipeline name")
    run_p.add_argument("sketch", help="sketch name")
    run_p.add_argument("--image", metavar="STEM", default=None,
                       help="image stem to process (default: all images in sketch)")

    sub.add_parser("list-sketches", help="list available sketches")
    sub.add_parser("list-pipelines", help="list available pipelines")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "list-sketches":
        cmd_list_sketches(args)
    elif args.command == "list-pipelines":
        cmd_list_pipelines(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
