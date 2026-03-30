# C4 System Context Diagram

```mermaid
C4Context
    title System Context Diagram — mattpace.art Monorepo

    Person(artist, "Artist/Developer", "Authors sketches, tunes parameters, deploys site")
    Person(agent, "Coding Agent", "Writes framework and sketch code, runs tests and linter")
    Person(visitor, "Site Visitor", "Views published generative art")

    System(sketchbook, "Sketchbook", "Reactive DAG-based creative coding framework: pipeline engine, executor, dev server, build tooling, CLI")
    System(userland, "mattpace.art", "Userland sketches, static site, presets, and deployment config. Depends on Sketchbook.")

    System_Ext(github, "GitHub", "Code hosting, pull requests, GitHub Pages deployment")

    Rel(artist, sketchbook, "Runs dev server and build CLI, views pipeline outputs")
    Rel(artist, userland, "Authors sketches, tunes parameters locally")
    Rel(artist, github, "Deploys site")

    Rel(agent, sketchbook, "Writes framework code, runs tests and linter")
    Rel(agent, userland, "Writes pipeline steps, implements sketches")
    Rel(agent, github, "Pushes branches, creates PRs")

    Rel(visitor, userland, "Views published generative art")

    Rel(userland, sketchbook, "Depends on", "Python package")
    Rel(userland, github, "Hosted and deployed via", "Git + GitHub Pages")
```

# C4 Container Diagram

```mermaid
C4Container
    title Container Diagram — mattpace.art Monorepo

    Person(artist, "Artist/Developer", "Authors sketches, tunes parameters, deploys site")
    Person(agent, "Coding Agent", "Writes framework and sketch code, runs tests and linter")
    Person(visitor, "Site Visitor", "Views published generative art")

    System_Ext(github, "GitHub", "Code hosting, pull requests, GitHub Pages deployment")

    System_Boundary(sketchbook, "Sketchbook (Framework)") {
        Container(dag_engine, "DAG Engine", "Python", "Core library: DAG, executor, pipeline steps, types, params, presets")
        Container(dev_server, "Dev Server", "FastAPI, Jinja2, WebSocket", "Serves pipeline outputs, Tweakpane parameter UI, live reload")
        Container(bundle_builder, "Bundle Builder", "Python", "Executes presets across sketches, writes output images and manifest.json")
    }

    System_Boundary(userland, "mattpace.art (Userland)") {
        Container(sketches, "Sketches", "Python", "Pipeline step implementations, assets, presets")
        Container(static_site, "Static Site", "11ty", "Generated pages for published art, reads bundle manifest")
        Container(mise, "Mise Task Runner", "TOML config, shell scripts", "Orchestrates dev, build, deploy, and authoring tasks")
    }

    Rel(artist, dev_server, "Tunes parameters, views pipeline outputs", "Browser")
    Rel(artist, mise, "Runs dev, build, deploy, authoring tasks", "CLI")

    Rel(agent, sketches, "Writes pipeline steps, implements sketches")
    Rel(agent, dag_engine, "Writes framework code, runs tests")
    Rel(agent, github, "Pushes branches, creates PRs")

    Rel(visitor, static_site, "Views published generative art", "HTTPS")

    Rel(dev_server, dag_engine, "Executes pipelines, serves intermediates")
    Rel(bundle_builder, dag_engine, "Executes pipelines to produce outputs")

    Rel(sketches, dag_engine, "Imports PipelineStep, Sketch base classes", "Python package")
    Rel(static_site, bundle_builder, "Reads manifest.json and output images", "Filesystem")

    Rel(mise, dev_server, "Starts", "uv run dev")
    Rel(mise, bundle_builder, "Runs", "uv run build")
    Rel(mise, static_site, "Builds and deploys", "npm build, deploy.sh")

    Rel(static_site, github, "Deployed via", "GitHub Pages")
```
