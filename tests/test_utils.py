from pathlib import Path
from typing import Any, cast

import typer
from githubkit import GitHub
from respx import Route

from pyright_analysis_action._utils import pr_id_from_number, set_outputs


def test_set_outputs(tmp_path: Path):
    output_file = tmp_path / "outputs.txt"
    with output_file.open("w") as file:
        set_outputs(cast(typer.FileTextWrite, file), foo="bar baz", ham="spammy 1 2 3")
    assert output_file.read_text() == "foo=bar baz\nham=spammy 1 2 3\n"


async def test_pr_id_from_number(github: GitHub[Any], graphql_mock: Route) -> None:
    graphql_mock.respond(json={"data": {"node": {"pullRequest": {"id": "foobar"}}}})
    result = await pr_id_from_number(github, "barfoo", 42)
    assert result == "foobar"
