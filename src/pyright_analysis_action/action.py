import asyncio
import os
from typing import Annotated

import typer
from pyright_analysis import schema, treemap

from ._smoketest import SmokeTest
from .smokeshow import upload
from .utils import set_outputs

app = typer.Typer(
    context_settings=dict(auto_envvar_prefix="INPUT"),
    add_completion=False,
    pretty_exceptions_enable=bool(os.environ.get("RUNNER_DEBUG")),
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
    embeddable: Annotated[bool, typer.Option()] = False,
    div_id: Annotated[str | None, typer.Option()] = None,
    step_summary: Annotated[
        typer.FileTextWrite | None, typer.Option(envvar="GITHUB_STEP_SUMMARY")
    ] = None,
    output: Annotated[
        typer.FileTextWrite | None, typer.Option(envvar="GITHUB_OUTPUT")
    ] = None,
    smokeshow_auth_key: Annotated[
        str | None, typer.Option(envvar="SMOKESHOW_AUTH_KEY")
    ] = None,
    _smoketest: SmokeTest = None,
) -> None:
    data = report.read()
    results = schema.PyrightJsonResults.model_validate_json(data)
    figure = treemap.to_treemap(results.type_completeness)

    html_page: str = figure.to_html(full_html=not embeddable, div_id=div_id)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(html_page, str)
    preview = figure.to_image("svg", scale=0.5)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    assert isinstance(preview, bytes)

    expiration, html_url, preview_url = asyncio.run(
        upload(smokeshow_auth_key, html_page, preview)
    )

    package_name = results.type_completeness.package_name
    summary = SUMMARY_MESSAGE.format(
        package_name=package_name,
        html_url=html_url,
        preview_url=preview_url,
        expiration=expiration.isoformat(timespec="seconds"),
    )
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
        )

    typer.secho("Report generated", fg="green", bold=True)
