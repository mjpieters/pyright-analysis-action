# GraphQL queries and the type definitions for their input and output data
import datetime
from collections.abc import AsyncIterator, Mapping
from typing import Any, ClassVar, TypedDict, cast

from githubkit import GitHub

type JSONAny = JSONScalar | JSONArray | JSONObject
type JSONScalar = str | bool | float | int | None
type JSONArray = list[JSONAny]
type JSONObject = dict[str, JSONAny]


def _unwrap_singles(obj: JSONAny, *drop: str) -> JSONAny:
    """Remove single-key dictionary wrappers"""
    drop_keys = set(drop)
    while isinstance(obj, dict) and len(obj.keys() - drop_keys) == 1:
        obj = next(v for k, v in obj.items() if k not in drop_keys)
    return obj


class GQLQueryBase[S: Mapping[str, Any], T]:
    _query: ClassVar[str]

    def __init__(self, client: GitHub[Any]) -> None:
        self._client = client

    async def _execute(self, variables: S) -> T:
        result = await self._client.graphql.arequest(self._query, dict(variables))
        return cast(T, _unwrap_singles(result))

    async def _execute_paged(self, variables: S) -> AsyncIterator[T]:
        async for page in self._client.graphql.paginate(self._query, dict(variables)):
            yield cast(T, _unwrap_singles(page, "pageInfo"))


class GQLQuery[S: Mapping[str, Any], T](GQLQueryBase[S, T]):
    async def __call__(self, variables: S) -> T:
        return await self._execute(variables)


class GQLPagedQuery[S: Mapping[str, Any], T](GQLQueryBase[S, T]):
    def __call__(self, variables: S) -> AsyncIterator[T]:
        return self._execute_paged(variables)


class _MutationInput[T](TypedDict):
    input: T


class GQLMutation[S: Mapping[str, Any], T](GQLQueryBase[_MutationInput[S], T]):
    async def __call__(self, inputs: S) -> T:
        return await self._execute({"input": inputs})


class _Connection[T](TypedDict):
    nodes: list[T]


class _Node(TypedDict):
    id: str


class _SparseCommit(TypedDict):
    oid: str


class _SparseHeadRefForcePushedEvent(TypedDict):
    beforeCommit: _SparseCommit


class _SparsePullRequestCommit(TypedDict):
    commit: _SparseCommit


class _SparsePullRequest(TypedDict):
    id: str
    headRefOid: str
    headRepository: _Node
    timelineItems: _Connection[_SparseHeadRefForcePushedEvent]
    commits: _Connection[_SparsePullRequestCommit]


class _PrsForBranchVariables(TypedDict):
    repository_id: str
    headRefName: str
    since: datetime.datetime | None


class PrsForBranchQuery(GQLQuery[_PrsForBranchVariables, list[_SparsePullRequest]]):
    """Find PRs for a given workflow_run.

    This queries for PRs with a given branch name against a given repository.
    This initially filters on the base repository node id plus the name of the
    head branch being merged. Per PR we include the first force-push events added
    after the source workflow was created, and the last 100 commits in the PR
    branch. The returned information can then be used to narrow down the exact
    PR, because we can then confirm the head repository matches, and we can look
    for an exact head reference match against either the last known head sha or
    a known commit sha.

    There is no pagination; if there are more than 100 PRs that all have the
    same head branch name in a single repository, and we can't find a matching
    head sha in the 100 most-recent commits, then something really extreme is going
    on ¯\\_(ツ)_/¯.
    """

    _query = """
    query PrsForBranch($repository_id: ID!, $headRefName: String!, $since: DateTime) {
        node(id: $repository_id) {
            ... on Repository {
                pullRequests(
                    headRefName: $headRefName
                    first: 100
                    orderBy: {field: UPDATED_AT, direction: DESC}
                ) {
                    nodes {
                        id
                        headRefOid
                        headRepository { id }
                        timelineItems(
                            since: $since
                            itemTypes: [HEAD_REF_FORCE_PUSHED_EVENT]
                            first: 1
                        ) {
                            nodes {
                                ... on HeadRefForcePushedEvent {
                                    beforeCommit { oid }
                                }
                            }
                        }
                        commits(last: 100) {
                            nodes { commit { oid } }
                        }
                    }
                }
            }
        }
    }
    """


class _SparseIssueComment(TypedDict):
    id: str
    isMinimized: bool
    viewerDidAuthor: bool
    body: str


class _CommentsForPrVariables(TypedDict):
    pr_id: str
    """The node id of the PR to fetch comments for"""


class CommentsForPrQuery(
    GQLPagedQuery[_CommentsForPrVariables, list[_SparseIssueComment]]
):
    """Fetch comments for a given PR."""

    _query = """
    query CommentsForPR($pr_id: ID!, $cursor: String) {
        node(id: $pr_id) {
            ... on PullRequest {
                comments(first: 100, after: $cursor) {
                    nodes {
                        id
                        isMinimized
                        viewerDidAuthor
                        body
                    }
                    pageInfo {
                        endCursor
                        hasNextPage
                    }
                }
            }
        }
    }
    """


class _PullRequestIdVariables(TypedDict):
    repository_id: str
    number: int


class PullRequestIdQuery(GQLQuery[_PullRequestIdVariables, str]):
    """Map a PR number in a given repository id to a PR node id"""

    _query = """
    query PullRequestId($repository_id: ID!, $number: Int!) {
        node(id: $repository_id) {
            ... on Repository {
                pullRequest(number: $number) { id }
            }
        }
    }
    """


class _UpdateCommentVariables(TypedDict):
    id: str
    body: str


class UpdateCommentMutation(GQLMutation[_UpdateCommentVariables, str]):
    _query = """
    mutation UpdateComment($input: UpdateIssueCommentInput!) {
        updateIssueComment(input: $input) {
            issueComment { url }
        }
    }
    """


class _AddCommentVariables(TypedDict):
    subjectId: str
    body: str


class AddCommentMutation(GQLMutation[_AddCommentVariables, str]):
    _query = """
    mutation AddComment($input: AddCommentInput!) {
        addComment(input: $input) {
            commentEdge { node { url } }
        }
    }
    """
