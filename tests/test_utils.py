from pathlib import Path
from typing import cast

import typer

from pyright_analysis_action.utils import set_outputs


def test_set_outputs(tmp_path: Path):
    output_file = tmp_path / "outputs.txt"
    with output_file.open("w") as file:
        set_outputs(cast(typer.FileTextWrite, file), foo="bar baz", ham="spammy 1 2 3")
    assert output_file.read_text() == "foo=bar baz\nham=spammy 1 2 3\n"
