# Pyright Analysis Action

Generate a [Pyright Analysis type compleness visualisation](https://github.org/mjpieters/pyright-analysis) in your Python project Github workflows, and share this graph in a PR comment or the workflow summary, from a [pyright type compleness report](https://microsoft.github.io/pyright/#/typed-libraries?id=verifying-type-completeness).

## Usage

Generate a type compleness report for your project, and pass it to
this action:

```yaml
name: Type Compleness graph

on:
  push:
    branches:
      - master
  pull_request:

permissions:
  content: read

env:
  PROJECT_NAME: 'your_python_project'

jobs:
  generate_graph:
    runs-on: ubuntu-latest
    permisions:
      pull-requests: write # To post comments

    steps:
    - uses: actions/checkout@v4.2.2
      
    - name: Install uv
      uses: astral-sh/setup-uv@v5.1.0
    
    - name: Generate report JSON
      run: |
        # Generate the type compleness report for your Python project.
        # This assumes your Python project can be installed as editable
        # from files in the current directory
        uv tool run --with-editable . pyright \
          --ignoreexternal --outputjson \
          --verifytypes $PROJECT_NAME > type_compleness_report.json

    - name: Generate report visualisation
      uses: mjpieters/pyright-analysis-action@v1
      env:
        # Smokeshow authorisation key for your project. Optional, but recommended.
        # See documentation for how to get one.
        SMOKESHOW_AUTH_KEY: ${{ secret.SMOKESHOW_AUTH_KEY }}
      with:
          report: type_compleness_report.json
```

This outputs a preview image and a link in the workflow summary page.

## Smokeshow authorisation key

The generated graph is published using [smokeshow](https://smokeshow.helpmanual.io/), a service for publishing ephemeral HTML reports. Graphs are kept for 1 year.

Publishing requires an authorisation key, which you can generate by running the `smokeshow` command-line utility. If you have [`uv`](https://docs.astral.sh/uv/) installed, simply run:

```shell
uvx smokeshow generate-key
```

The pyright analysis action looks for a `SMOKESHOW_AUTH_KEY` environment variable when publishing. It will generate a new key if none is set, but take into account that generating a new key every time can take several minutes each run.

## Inputs

| name | required | description |
|------|----------|-------------|
| `report` | yes | Path to the Pyright verifytypes report. Must be in JSON format, so produced with the `--outputjson` flag. |
| `embeddable` | |  Normally, the graph is generated as a full, stand-alone HTML file. If you want to embed the graph in a larger web page, set this option to 'true' (or '1', 'on', or 'yes') to only output the report in a `<div>` tag. Note that when you provide a page template, this option is ignored. |
| `div_id` | | Provide a value for the `<div>` tag that wraps the report in the generated HTML page. If omitted, a random UUID is used. |

## Outputs

| name | description |
|------|-------------|
| `html_url` | The URL of the interactive graph. |
| `preview_url` | The URL of the preview image (SVG). |
| `expiration` | ISO8601-formatted date time value for when the published page expires. |

<!--
TODO:
 - only in Linux workflows
 - implement commenting
 - toggle commenting
 - toggle summary report
 - write html to file?
 - write image to file?
-->