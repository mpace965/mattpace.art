# Domain Docs

How the engineering skills should consume this repo's domain documentation.

## Before exploring, read these

This is a multi-context monorepo. Read the `CONTEXT.md` for each sub-project relevant to your task:

- `framework/CONTEXT.md` — DAG engine, executor, dev server, CLI (the Sketchbook package)
- `sketches/CONTEXT.md` — userland creative modules and sketch conventions
- `site/CONTEXT.md` — Eleventy static site, JS/Node stack

Also read:

- `docs/adr/` — system-wide architectural decisions
- `docs/audits/` — recent code quality audits with substantive findings; treat as live context

Ignore `docs/initial-implementation-plan.md`, `docs/v3-*.md`, `docs/parallel-variants-plan.md`, `docs/increment-*.md`, and `docs/spike_proxy_mechanism.py` — these are historical planning artifacts.

If any CONTEXT.md files don't exist yet, proceed silently.

## File structure

```
/
├── CONTEXT-MAP.md
├── docs/adr/          ← system-wide decisions
├── docs/audits/       ← live code quality context
├── framework/
│   └── CONTEXT.md
├── sketches/
│   └── CONTEXT.md
└── site/
    └── CONTEXT.md
```

## Use the glossary's vocabulary

When your output names a domain concept, use the term as defined in the relevant `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding.
