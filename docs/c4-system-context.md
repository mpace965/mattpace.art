# C4 System Context Diagram

```mermaid
---
title: System Context — mattpace.art Monorepo
---
flowchart TD
    artist["🧑‍🎨 Artist/Developer\n\nAuthors sketches, tunes\nparameters, deploys site"]
    agent["🤖 Coding Agent\n\nWrites framework and sketch\ncode, runs tests and linter"]
    visitor["👤 Site Visitor\n\nViews published\ngenerative art"]

    sketchbook["Sketchbook\n\nReactive DAG-based creative\ncoding framework: pipeline engine,\nexecutor, dev server, build tooling, CLI"]
    userland["mattpace.art\n\nUserland sketches, static site,\npresets, and deployment config"]

    github[("GitHub\n\nCode hosting, PRs,\nGitHub Pages")]

    artist -->|"Runs dev server\nand build CLI"| sketchbook
    artist -->|"Authors sketches,\ntunes parameters"| userland
    artist -->|"Deploys site"| github

    agent -->|"Writes framework\ncode, runs tests"| sketchbook
    agent -->|"Writes pipeline\nsteps"| userland
    agent -->|"Pushes branches,\ncreates PRs"| github

    visitor -->|"Views published art"| userland

    userland -->|"Depends on\n(Python package)"| sketchbook
    userland -->|"Deployed via\nGitHub Pages"| github

    style artist fill:#08427b,color:#fff,stroke:#073b6e
    style agent fill:#999,color:#fff,stroke:#777
    style visitor fill:#08427b,color:#fff,stroke:#073b6e
    style sketchbook fill:#1168bd,color:#fff,stroke:#0e5aa7
    style userland fill:#1168bd,color:#fff,stroke:#0e5aa7
    style github fill:#666,color:#fff,stroke:#555
```

# C4 Container Diagram

```mermaid
---
title: Container Diagram — mattpace.art Monorepo
---
flowchart TD
    artist["🧑‍🎨 Artist/Developer"]
    agent["🤖 Coding Agent"]
    visitor["👤 Site Visitor"]
    github[("GitHub\nCode hosting, PRs, GitHub Pages")]

    subgraph sketchbook ["Sketchbook (Framework)"]
        dag_engine["DAG Engine\n\nPython\nDAG, executor, pipeline steps,\ntypes, params, presets"]
        dev_server["Dev Server\n\nFastAPI\nPipeline outputs, Tweakpane UI,\nWebSocket live reload"]
        bundle_builder["Bundle Builder\n\nPython\nExecutes presets, writes output\nimages and manifest"]
    end

    subgraph userland ["mattpace.art (Userland)"]
        sketches["Sketches\n\nPython\nPipeline step implementations,\nassets, presets"]
        static_site["Static Site\n\n11ty\nPublished art pages,\nreads bundle manifest"]
        mise["Mise Task Runner\n\nTOML, shell\nOrchestrates dev, build,\ndeploy tasks"]
    end

    artist -->|"Tunes params,\nviews outputs (Browser)"| dev_server
    artist -->|"Runs dev, build,\ndeploy (CLI)"| mise

    agent -->|"Writes pipeline steps"| sketches
    agent -->|"Writes framework code"| dag_engine
    agent -->|"Pushes branches,\ncreates PRs"| github

    visitor -->|"Views published\nart (HTTPS)"| static_site

    dev_server -->|"Executes pipelines"| dag_engine
    bundle_builder -->|"Executes pipelines"| dag_engine

    sketches -->|"Imports base classes\n(Python package)"| dag_engine
    static_site -->|"Reads manifest\nand images"| bundle_builder

    mise -->|"uv run dev"| dev_server
    mise -->|"uv run build"| bundle_builder
    mise -->|"npm build,\ndeploy.sh"| static_site

    static_site -->|"Deployed via\nGitHub Pages"| github

    style artist fill:#08427b,color:#fff,stroke:#073b6e
    style agent fill:#999,color:#fff,stroke:#777
    style visitor fill:#08427b,color:#fff,stroke:#073b6e
    style github fill:#666,color:#fff,stroke:#555

    style dag_engine fill:#1168bd,color:#fff,stroke:#0e5aa7
    style dev_server fill:#1168bd,color:#fff,stroke:#0e5aa7
    style bundle_builder fill:#1168bd,color:#fff,stroke:#0e5aa7

    style sketches fill:#438dd5,color:#fff,stroke:#3c7fc0
    style static_site fill:#438dd5,color:#fff,stroke:#3c7fc0
    style mise fill:#438dd5,color:#fff,stroke:#3c7fc0

    style sketchbook fill:none,stroke:#0e5aa7,stroke-width:2px,color:#0e5aa7
    style userland fill:none,stroke:#3c7fc0,stroke-width:2px,color:#3c7fc0
```
