import asyncio
import logging
import os
import re
from typing import Annotated

import click
import typer
from githubkit import ActionAuthStrategy, GitHub
from pyright_analysis import schema, treemap

from ._smoketest import SmokeTest
from ._utils import set_outputs
from .comment import Commenter, NotCommenting
from .smokeshow import upload

DEBUG = bool(os.environ.get("RUNNER_DEBUG"))
TEMPLATE_SLOT = re.compile(r"\{\{\s*graph\s*\}\}")

app = typer.Typer(
    context_settings=dict(auto_envvar_prefix="INPUT"),
    add_completion=False,
    pretty_exceptions_enable=DEBUG,
)


SUMMARY_MESSAGE = """\
## Pyright Type Completeness Visualisation

View the [interactive graph for `{package_name}`]({html_url}).

[![preview graph]({preview_url})]({html_url})

*Page available until {expiration}.*
"""


@app.command()
def action(
    report: Annotated[typer.FileText, typer.Argument(envvar="INPUT_REPORT")],
    div_id: Annotated[str | None, typer.Option()] = None,
    template: Annotated[str | None, typer.Option()] = None,
    template_file: Annotated[typer.FileText | None, typer.Option()] = None,
    comment_on_pr: Annotated[bool, typer.Option()] = False,
    smokeshow_auth_key: Annotated[
        str | None, typer.Option(envvar="SMOKESHOW_AUTH_KEY")
    ] = None,
    step_summary: Annotated[
        typer.FileTextWrite | None, typer.Option(envvar="GITHUB_STEP_SUMMARY")
    ] = None,
    output: Annotated[
        typer.FileTextWrite | None, typer.Option(envvar="GITHUB_OUTPUT")
    ] = None,
    event_name: Annotated[str | None, typer.Option(envvar="GITHUB_EVENT_NAME")] = None,
    event_file: Annotated[
        typer.FileText | None, typer.Option(envvar="GITHUB_EVENT_PATH")
    ] = None,
    api_url: Annotated[str | None, typer.Option(envvar="GITHUB_API_URL")] = None,
    workflow: Annotated[str | None, typer.Option(envvar="GITHUB_WORKFLOW")] = None,
    jobid: Annotated[str | None, typer.Option(envvar="GITHUB_JOB")] = None,
    _smoketest: SmokeTest = None,
) -> None:
    if template is not None and template_file is not None:
        raise click.UsageError(
            "Provide either a template string or a template file, not both"
        )
    if template is None and template_file is not None:
        template = template_file.read()
    if template is not None and TEMPLATE_SLOT.search(template) is None:
        raise click.UsageError(
            "Can't find a '{{ graph }}' slot in the provided template."
        )

    async def process_graph() -> None:
        data = report.read()
        results = schema.PyrightJsonResults.model_validate_json(data)
        figure = treemap.to_treemap(results.type_completeness)

        html_page: str = figure.to_html(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            div_id=div_id, full_html=(template is None), include_plotlyjs="cdn"
        )
        assert isinstance(html_page, str)
        if template is not None:
            html_page = TEMPLATE_SLOT.sub(html_page, template, 1)

        preview = figure.to_image("svg", scale=0.5)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        assert isinstance(preview, bytes)

        expiration, html_url, preview_url = await upload(
            smokeshow_auth_key, html_page, preview
        )

        package_name = results.type_completeness.package_name
        summary = SUMMARY_MESSAGE.format(
            package_name=package_name,
            html_url=html_url,
            preview_url=preview_url,
            expiration=expiration.isoformat(timespec="seconds"),
        )

        comment_url = None
        if comment_on_pr and event_name and event_file:
            with GitHub(ActionAuthStrategy(), base_url=api_url) as client:
                try:
                    commenter = await Commenter.from_event(
                        client, event_name, event_file, workflow=workflow, jobid=jobid
                    )
                except NotCommenting as exc:
                    typer.secho(
                        f"Skipping posting a PR comment: {exc.reason}", dim=True
                    )
                else:
                    comment_url = await commenter.post_or_update_comment(summary)
                    typer.secho(f"Comment posted or updated at {comment_url}")

        if step_summary:  # pragma: no cover
            step_summary.write(summary)
        else:
            typer.secho("\nSummary:", fg="cyan", bold=True)
            typer.echo(f"\n{summary}")

        if output:
            set_outputs(
                output,
                html_url=html_url,
                preview_url=preview_url,
                expiration=expiration.isoformat(),
                comment_url=comment_url,
            )

    logging.basicConfig(level=logging.DEBUG if DEBUG else logging.INFO)

    asyncio.run(process_graph())

    typer.secho("Report generated", fg="green", bold=True)
