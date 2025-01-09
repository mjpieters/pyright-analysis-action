from typing import Any

import typer
from githubkit import GitHub

from pyright_analysis_action._graphql import PullRequestIdQuery


def set_outputs(output: typer.FileTextWrite, **kwargs: Any) -> None:
    outputs = "\n".join([f"{name}={value}" for name, value in kwargs.items()])
    output.write(f"{outputs}\n")


async def pr_id_from_number(client: GitHub[Any], id: str, number: int) -> str:
    return await PullRequestIdQuery(client)({"repository_id": id, "number": number})
