from typing import Any

import typer


def set_outputs(output: typer.FileTextWrite, **kwargs: Any) -> None:
    outputs = "\n".join([f"{name}={value}" for name, value in kwargs.items()])
    output.write(f"{outputs}\n")
