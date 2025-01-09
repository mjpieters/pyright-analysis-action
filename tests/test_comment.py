from datetime import UTC, datetime
from io import StringIO
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from githubkit import GitHub
from respx import Route
from typer import FileText

from pyright_analysis_action.comment import (
    Commenter,
    NotCommenting,
    pr_from_workflow_run,
)


def _prs_node(
    repo_id: str, pr_id: str, *commits: str, force_push: str | None = None
) -> dict[str, Any]:
    commits = commits or ("deadbeefcoffeefeedcafec0ded00dfa1l5afe42",)
    timeline = [{"beforeCommit": {"oid": force_push}}] if force_push else []
    return {
        "id": pr_id,
        "headRefOid": commits[-1],
        "headRepository": {"id": repo_id},
        "timelineItems": {"nodes": timeline},
        "commits": {"nodes": [{"commit": {"oid": commit}} for commit in commits]},
    }


def _prs_for_branch_base(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"node": {"pullRequests": {"nodes": list(nodes)}}}}


@pytest.fixture
def single_entry_response() -> dict[str, Any]:
    return _prs_for_branch_base(_prs_node("R_head_repository", "PR_target"))


@pytest.fixture
def separate_repositories_response() -> dict[str, Any]:
    return _prs_for_branch_base(
        _prs_node("R_head_repository", "PR_target"),
        _prs_node("R_some_other_repo", "PR_wrong_target"),
    )


@pytest.fixture
def multiple_prs_response() -> dict[str, Any]:
    return _prs_for_branch_base(
        _prs_node(
            "R_head_repository",
            "PR_wrong_target",
            "0aad69efa8f32199f5eb0bdf8b0bb17928167251",
            force_push="680c0703082f432a282ccee847661c5927efb785",
        ),
        _prs_node(
            "R_head_repository",
            "PR_target",
            "a2b5cddc27ee26bd7ea1982bebc7fb43fe7de789",
        ),
    )


class TestPrFromWorkflow:
    async def test_no_matches(
        self,
        github: GitHub[Any],
        graphql_mock: Route,
        single_entry_response: dict[str, Any],
    ) -> None:
        graphql_mock.respond(json=single_entry_response)
        result = await pr_from_workflow_run(
            github,
            "R_somerepo",
            "R_not_a_listed_repo",
            "some_branch_name",
            "a2b5cddc27ee26bd7ea1982bebc7fb43fe7de789",
            created_at=datetime.now(UTC),
        )
        assert result is None

    async def test_single_entry(
        self,
        github: GitHub[Any],
        graphql_mock: Route,
        single_entry_response: dict[str, Any],
    ) -> None:
        graphql_mock.respond(json=single_entry_response)
        result = await pr_from_workflow_run(
            github,
            "R_somerepo",
            "R_head_repository",
            "some_branch_name",
            "a2b5cddc27ee26bd7ea1982bebc7fb43fe7de789",
            created_at=datetime.now(UTC),
        )
        assert result == "PR_target"

    async def test_multiple_repos(
        self,
        github: GitHub[Any],
        graphql_mock: Route,
        separate_repositories_response: dict[str, Any],
    ) -> None:
        graphql_mock.respond(json=separate_repositories_response)
        result = await pr_from_workflow_run(
            github,
            "R_somerepo",
            "R_head_repository",
            "some_branch_name",
            "a2b5cddc27ee26bd7ea1982bebc7fb43fe7de789",
            created_at=datetime.now(UTC),
        )
        assert result == "PR_target"

    async def test_multiple_prs(
        self,
        github: GitHub[Any],
        graphql_mock: Route,
        multiple_prs_response: dict[str, Any],
    ) -> None:
        graphql_mock.respond(json=multiple_prs_response)
        result = await pr_from_workflow_run(
            github,
            "R_somerepo",
            "R_head_repository",
            "some_branch_name",
            "a2b5cddc27ee26bd7ea1982bebc7fb43fe7de789",
            created_at=datetime.now(UTC),
        )
        assert result == "PR_target"


class TestCommenterFromEvent:
    event_file = cast(FileText, StringIO())

    @pytest.mark.parametrize(
        "event_name,event",
        (
            ("push", None),
            (
                "workflow_run",
                Mock(workflow_run=Mock(event="push")),
            ),
            (
                "workflow_run",
                Mock(
                    workflow_run=Mock(
                        event="pull_request", pull_requests=[], head_branch=None
                    )
                ),
            ),
            (
                "workflow_run",
                Mock(
                    workflow_run=Mock(
                        event="pull_request",
                        pull_requests=[],
                        head_branch="some_branch",
                    )
                ),
            ),
        ),
    )
    async def test_not_commenting(self, event_name: str, event: Any) -> None:
        with (
            patch(
                "pyright_analysis_action.comment.parse",
                autospec=True,
                return_value=event,
            ),
            patch(
                "pyright_analysis_action.comment.pr_from_workflow_run",
                autospec=True,
                return_value=None,
            ),
            pytest.raises(NotCommenting),
        ):
            await Commenter.from_event(Mock(), event_name, self.event_file)

    async def test_from_pull_request(self) -> None:
        with (
            patch(
                "pyright_analysis_action.comment.parse",
                autospec=True,
                return_value=Mock(repository=Mock(node_id="R_node_id"), number=42),
            ),
            patch(
                "pyright_analysis_action.comment.pr_id_from_number",
                autospec=True,
                return_value="PR_node_id",
            ),
        ):
            instance = await Commenter.from_event(
                Mock(), "pull_request", self.event_file
            )
        assert instance.pr == "PR_node_id"

    async def test_from_workflow_run_pull_requests(self) -> None:
        with (
            patch(
                "pyright_analysis_action.comment.parse",
                autospec=True,
                return_value=Mock(
                    workflow_run=Mock(
                        event="pull_request",
                        pull_requests=[Mock(number=42)],
                    ),
                    repository=Mock(node_id="R_node_id"),
                ),
            ),
            patch(
                "pyright_analysis_action.comment.pr_id_from_number",
                autospec=True,
                return_value="PR_node_id",
            ),
        ):
            instance = await Commenter.from_event(
                Mock(), "workflow_run", self.event_file
            )
        assert instance.pr == "PR_node_id"

    async def test_from_workflow_run_from_head_branch(self) -> None:
        with (
            patch(
                "pyright_analysis_action.comment.parse",
                autospec=True,
                return_value=Mock(
                    workflow_run=Mock(
                        event="pull_request",
                        pull_requests=[],
                        head_branch="some_branch",
                    ),
                    repository=Mock(node_id="R_node_id"),
                ),
            ),
            patch(
                "pyright_analysis_action.comment.pr_from_workflow_run",
                autospec=True,
                return_value="PR_node_id",
            ),
        ):
            instance = await Commenter.from_event(
                Mock(), "workflow_run", self.event_file
            )
        assert instance.pr == "PR_node_id"


def test_comment_marker():
    commenter = Commenter(Mock(), "PR_node_id", foo="bar", baz=None)
    assert commenter.comment_marker == "<!-- pyright-analysis-action foo='bar' -->"


class TestExistingComment:
    async def test_none_matching(
        self, github: GitHub[Any], graphql_mock: Route
    ) -> None:
        commenter = Commenter(github, "PR_node_id", worflow="mock_flow")
        graphql_mock.respond(
            json={
                "data": {
                    "node": {
                        "comments": {
                            "nodes": [
                                {
                                    "id": "IC_comment1",
                                    "isMinimized": True,
                                    "viewerDidAuthor": True,
                                    "body": "First comment\n\n"
                                    + commenter.comment_marker,
                                },
                                {
                                    "id": "IC_comment2",
                                    "isMinimized": False,
                                    "viewerDidAuthor": False,
                                    "body": "Second comment",
                                },
                                {
                                    "id": "IC_comment3",
                                    "isMinimized": False,
                                    "viewerDidAuthor": True,
                                    "body": "Third comment",
                                },
                                {
                                    "id": "IC_comment4",
                                    "isMinimized": False,
                                    "viewerDidAuthor": True,
                                    "body": "Last comment\n\n"
                                    + commenter.comment_marker.replace("mock", "spam"),
                                },
                            ],
                            "pageInfo": {"endCursor": "Opaque", "hasNextPage": False},
                        }
                    }
                }
            }
        )
        assert await commenter.existing_comment_id() is None

    async def test_matching(self, github: GitHub[Any], graphql_mock: Route) -> None:
        commenter = Commenter(github, "PR_node_id", workflow="mock_flow")
        graphql_mock.respond(
            json={
                "data": {
                    "node": {
                        "comments": {
                            "nodes": [
                                {
                                    "id": "IC_node_id",
                                    "isMinimized": False,
                                    "viewerDidAuthor": True,
                                    "body": "First comment\n\n"
                                    + commenter.comment_marker,
                                },
                            ],
                            "pageInfo": {"endCursor": "Opaque", "hasNextPage": False},
                        }
                    }
                }
            }
        )
        assert await commenter.existing_comment_id() == "IC_node_id"


class TestCommenterPost:
    async def test_existing(self):
        commenter = Commenter(Mock(), "PR_node_id", foo="bar")
        with (
            patch.object(
                commenter,
                "existing_comment_id",
                autospec=True,
                return_value="IC_node_id",
            ),
            patch.object(
                commenter, "_update_comment", new=AsyncMock(return_value="return_value")
            ),
        ):
            assert await commenter.post_or_update_comment("summary") == "return_value"

    async def test_new(self):
        commenter = Commenter(Mock(), "PR_node_id", foo="bar")
        with (
            patch.object(
                commenter, "existing_comment_id", autospec=True, return_value=None
            ),
            patch.object(
                commenter, "_add_comment", new=AsyncMock(return_value="return_value")
            ),
        ):
            assert await commenter.post_or_update_comment("summary") == "return_value"
