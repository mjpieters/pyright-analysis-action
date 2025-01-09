import datetime
from typing import Any, Self

import typer
from githubkit import GitHub
from githubkit.webhooks import parse

from ._graphql import (
    AddCommentMutation,
    CommentsForPrQuery,
    PrsForBranchQuery,
    UpdateCommentMutation,
)
from ._utils import pr_id_from_number


class NotCommenting(Exception):
    """Exception raised when no PR could be found to comment on"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Commenter:
    @classmethod
    async def from_event(
        cls,
        client: GitHub[Any],
        event_name: str,
        event_file: typer.FileText,
        **context: str | None,
    ) -> Self:
        match event_name:
            case "pull_request" | "pull_request_target":
                event = parse("pull_request", event_file.read())
                node_id = await pr_id_from_number(
                    client, event.repository.node_id, event.number
                )
            case "workflow_run":
                event = parse(event_name, event_file.read())
                run = event.workflow_run
                if run.event not in {"pull_request", "pull_request_target"}:
                    raise NotCommenting(
                        "This workflow_run event was not triggered by a pull_request workflow"
                    )
                if any(run.pull_requests):
                    number = next(filter(None, run.pull_requests)).number
                    node_id = await pr_id_from_number(
                        client, event.repository.node_id, number
                    )
                elif (head_branch := run.head_branch) is None:
                    raise NotCommenting(
                        "No head branch reported for workflow_run parent workflow"
                    )
                else:
                    node_id = await pr_from_workflow_run(
                        client,
                        run.repository.node_id,
                        run.head_repository.node_id,
                        head_branch,
                        run.head_sha,
                        run.created_at,
                    )
                    if node_id is None:
                        raise NotCommenting("No PR found for this workflow_run event")

            case _:
                raise NotCommenting(
                    "Workflow was not triggered by a pull_request or "
                    f"workflow_run event ({event_name!r})"
                )
        return cls(client, node_id, **context)

    def __init__(
        self,
        client: GitHub[Any],
        pr_id: str,
        **context: str | None,
    ) -> None:
        self.pr = pr_id
        self.comment_context = context

        self._comments_for_pr_query = CommentsForPrQuery(client)
        self._update_comment = UpdateCommentMutation(client)
        self._add_comment = AddCommentMutation(client)

    @property
    def comment_marker(self) -> str:
        """HTML comment used to mark a comment as being from this action"""
        context = ", ".join(
            f"{name}={value!r}"
            for name, value in self.comment_context.items()
            if value is not None
        )
        return f"<!-- pyright-analysis-action {context} -->"

    async def existing_comment_id(self) -> str | None:
        """Find the node id of an existing comment"""
        marker = self.comment_marker
        async for page in self._comments_for_pr_query({"pr_id": self.pr}):
            try:
                return next(
                    cmt["id"]
                    for cmt in page
                    if cmt["viewerDidAuthor"]
                    and not cmt["isMinimized"]
                    and marker in cmt["body"]
                )
            except StopIteration:
                pass
        return None

    async def post_or_update_comment(self, summary: str) -> str:
        """Post or update a comment on this PR

        If a pre-existing comment is found, this is updated, otherwise a new
        comment is created. Returns the comment URL.
        """
        body = f"{summary}\n\n{self.comment_marker}"
        if comment_id := await self.existing_comment_id():
            # update
            return await self._update_comment({"id": comment_id, "body": body})
        else:
            # create
            return await self._add_comment({"subjectId": self.pr, "body": body})


async def pr_from_workflow_run(
    client: GitHub[Any],
    repo_id: str,
    head_repo_id: str,
    head_branch: str,
    head_sha: str,
    created_at: datetime.datetime,
) -> str | None:
    """Find the pull request number for a pull_request event.

    When a workflow_run workflow was triggered from a pull_request event, the
    `pull_events` list is often empty. Instead, query GithHub's GraphQL API for
    the corresponding PR information, given the base and head repository and
    head branch name.

    """
    # With GraphQL you can filter PRs in this (base) repo by the name of the
    # head branch of the PR. This is not necessarily a unique name, so we
    # have to narrow this down to the specific head repository _at least_.
    # Even then there can be multiple matches, due to closed or merged PRs.
    # For a given PR, the following information is fixed at PR creation:
    # - The base and head repositories
    # - The head branch name
    # Matching a head sha would be perfect, but the head sha can have changed
    # since the workflow started, with new commits or force pushes. Luckily, we
    # have full access to that information here.
    nodes = await PrsForBranchQuery(client)(
        {
            "repository_id": repo_id,
            "headRefName": head_branch,
            "since": created_at,
        },
    )
    # the head branch name may not be unique; the head repo owner must match too.
    filtered = [pr for pr in nodes if pr["headRepository"]["id"] == head_repo_id]
    if len(filtered) == 1:  # simple, just a single branch fits
        return filtered[0]["id"]

    # narrow it down by head ref
    for pr in filtered:
        refs = {pr["headRefOid"]} | {c["commit"]["oid"] for c in pr["commits"]["nodes"]}
        if timeline := pr["timelineItems"]["nodes"]:
            # the head ref at the time the workflow started before a force push changed it
            refs.add(timeline[0]["beforeCommit"]["oid"])
        if head_sha in refs:
            return pr["id"]

    # if we still can't figure it out, just pick the most recently updated.
    return filtered[0]["id"] if filtered else None
