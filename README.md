# Pyright Analysis Action

Generate a [Pyright Analysis type completeness visualisation](https://github.com/mjpieters/pyright-analysis) in your Python project Github workflows, and share this graph in a PR comment or the workflow summary, from a [pyright type completeness report](https://microsoft.github.io/pyright/#/typed-libraries?id=verifying-type-completeness).

## Usage

Generate a type completeness report for your project, and pass it to
this action:

```yaml
name: Type Completeness graph

on:
  push:
    branches:
      - master
  pull_request:

permissions:
  contents: read

env:
  PROJECT_NAME: 'your_python_project'

jobs:
  generate_graph:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4.2.2

    - name: Install uv
      uses: astral-sh/setup-uv@v5.1.0

    - name: Generate report JSON
      run: |
        # Generate the type completeness report for your Python project.
        # This assumes your Python project can be installed as editable
        # from files in the current directory
        uv tool run --with-editable . pyright \
          --ignoreexternal --outputjson \
          --verifytypes $PROJECT_NAME > type_completeness_report.json || true

    - name: Generate report visualisation
      uses: mjpieters/pyright-analysis-action@v0.2.0
      env:
        # Smokeshow authorisation key for your project. Optional, but recommended.
        # See documentation for how to get one.
        SMOKESHOW_AUTH_KEY: ${{ secrets.SMOKESHOW_AUTH_KEY }}
      with:
          report: type_completeness_report.json
```

This outputs a preview image and a link in the workflow summary page.

## Smokeshow authorisation key

The generated graph is published using [smokeshow](https://smokeshow.helpmanual.io/), a service for publishing ephemeral HTML reports. Graphs are kept for 1 year.

Publishing requires an authorisation key, which you can generate by running the `smokeshow` command-line utility. If you have [`uv`](https://docs.astral.sh/uv/) installed, simply run:

```shell
uvx smokeshow generate-key
```

The pyright analysis action looks for a `SMOKESHOW_AUTH_KEY` environment variable when publishing. It will generate a new key if none is set, but take into account that generating a new key every time can take several minutes each run.

## Commenting on Pull Requests

The action can post the summary as a comment on a triggering pull request, by setting `comment_on_pr` to `true`. You need to make sure that a github token with `pull-requests: write` permission is available. The latter means that you can't use this action in a `pull_requests` event when the PR is pushed from a fork of the repository, however.

If you want to support commenting on PRs from forks, you need to put this action
in a `workflow_run` workflow instead, which is triggered in response to a `pull_request`
workflow. Because it is not considered safe to run code from a forked repository,
you need to generate the pyright report in the `pull_request` workflow, upload the
result to an artefact, and then download the report in the `workflow_run` workflow.

Here is an example of such a setup. First the pull_request workflow to generate
the pyright JSON output. This runs in the context of the fork and won't have
access to any repository secrets:

```yaml
# pull_request.yml
name: "Generate Type Completeness Report"
on:
  pull_request:

permissions:
  contents: read

env:
  PROJECT_NAME: 'your_python_project'

jobs:
  generate_type_completeness_report:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4.2.2

    - name: Install uv
      uses: astral-sh/setup-uv@v5.1.0

    - name: Generate report JSON
      run: |
        # Generate the type completeness report for your Python project.
        # This assumes your Python project can be installed as editable
        # from files in the current directory
        uv tool run --with-editable . pyright \
          --ignoreexternal --outputjson \
          --verifytypes $PROJECT_NAME > type_completeness_report.json || true

    - name: Upload report JSON
      uses: actions/upload-artifact@v4
      with:
        name: type_completeness_report
        path: type_completeness_report.json
```

and then the follow-up workflow that runs in the context of your own repository,
and so can get write access to pull-requests:

```yaml
# workflow_run.yaml
on:
  workflow_run:
    workflows:
      - "Generate Type Completeness Report"
    types:
      - completed
  
permissions:
  contents: read

jobs:
  generate_graph:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'success' }}

    permissions:
      pull-requests: write

    steps:
    - name: Download report JSON
      uses: actions/download-artifact@v4
      with:
        name: type_completeness_report
        github-token: ${{ secrets.GITHUB_TOKEN }}
        run-id: ${{ github.event.workflow_run.id }}

    - name: Generate report visualisation
      uses: mjpieters/pyright-analysis-action@v0.2.0
      env:
        # Smokeshow authorisation key for your project. Optional, but recommended.
        # See documentation for how to get one.
        SMOKESHOW_AUTH_KEY: ${{ secrets.SMOKESHOW_AUTH_KEY }}
      with:
        report: type_completeness_report.json
        comment_on_pr: true

```

## Inputs

| name | required | description |
|------|----------|-------------|
| `report` | yes | Path to the Pyright verifytypes report. Must be in JSON format, so produced with the `--outputjson` flag. |
| `embeddable` | |  Normally, the graph is generated as a full, stand-alone HTML file. If you want to embed the graph in a larger web page, set this option to 'true' (or '1', 'on', or 'yes') to only output the report in a `<div>` tag. Note that when you provide a page template, this option is ignored. |
| `div_id` | | Provide a value for the `<div>` tag that wraps the report in the generated HTML page. If omitted, a random UUID is used. |
| `comment_on_pr` | | If set to `true` (or `yes`, or `1`, `t` or `y`), and the current workflow run was triggered by a `pull_request` or `workflow_run` event indirectly triggered by a `pull_request`, then a comment will be added to that pull request. If there already is a comment posted by this action then the existing comment is updated instead. Requires a github token with either `pull-requests: write` permission. Note that a `pull_request` workflow running in a forked repo will only get a read-only token so you'll need to put this action in a `workflow_run` workflow instead. See the action documentation for details. |
| `github_token` | | The github token to use when posting a comment on a PR. Defaults to the `GITHUB_TOKEN` secret for this workflow job. |

## Environment variables

| name | required | description |
|------|----------|-------------|
| `SMOKESHOW_AUTH_KEY` | | Authorisation key to use for HTML publishing. |


## Outputs

| name | description |
|------|-------------|
| `html_url` | The URL of the interactive graph. |
| `preview_url` | The URL of the preview image (SVG). |
| `expiration` | ISO8601-formatted date time value for when the published page expires. |
| `comment_url` | The URL of the posted comment, if any, null otherwise. |

## Runner requirements

This action is implemented as a [Docker container action](https://docs.github.com/en/actions/sharing-automations/creating-actions/about-custom-actions#docker-container-actions), which means that they can only be executed on Linux runners. From the linked Github documentation:

> Docker container actions can only execute on runners with a Linux operating system. Self-hosted runners must use a Linux operating system and have Docker installed to run Docker container actions. For more information about the requirements of self-hosted runners, see [About self-hosted runners](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners#requirements-for-self-hosted-runner-machines).

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) to handle Python dependencies and environments; use `uv sync` to get an up-to-date virtualenv with all dependencies. This includes development dependencies such as [Ruff](https://docs.astral.sh/ruff/) (used for linting and formatting) and [Pyright](https://microsoft.github.io/pyright/) (used to validate type annotations).

In addition, common tasks are defined in a taskfile; [install Task](https://taskfile.dev/) to use these. Run `task --list` to see what tasks are available.

### Linting and formatting

While PRs and commits on GitHub are checked for linting and formatting issues, it's easier to check for issues locally first. After running `uv sync`, run `uv run pre-commit install` or `task dev:install-precommit` to install [pre-commit](https://pre-commit.com/) hooks that will run these tools and format your changes automatically on commits. These hooks also run `uv sync` whenever you working tree changes.

The taskfile includes specific linting and formatting tasks.

### Testing

This project uses `pytest` to run its tests: `uv run pytest` or `task dev:test`
