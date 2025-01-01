from typing import Annotated

import typer
from pyright_analysis import schema, treemap


def smoketest(value: bool) -> None:
    if not value:
        return
    typer.secho("Action container smoketest", fg="yellow", bold=True, color=True)

    # convert a minimal report to SVG to verify the Chromium headless browser
    # works as expected
    counts = schema.SymbolCounts(
        with_known_type=0, with_ambiguous_type=0, with_unknown_type=0
    )
    test_report = schema.TypeCompletenessReport(
        package_name="foo",
        module_name=schema.SymbolName("foo"),
        ignore_unknown_types_from_imports=True,
        exported_symbol_counts=counts,
        other_symbol_counts=counts,
        missing_function_doc_string_count=0,
        missing_class_doc_string_count=0,
        missing_default_param_count=0,
        completeness_score=0,
        modules=[],
        symbols=[],
    )
    figure = treemap.to_treemap(test_report)
    figure.to_image("svg")  # pyright: ignore[reportUnknownMemberType]

    typer.secho("Test passed", fg="green", bold=True, color=True)
    raise typer.Exit(0)


SmokeTest = Annotated[
    bool | None,
    typer.Option(
        "--smoketest",
        callback=smoketest,
        is_eager=True,
        expose_value=False,
        hidden=True,
    ),
]
