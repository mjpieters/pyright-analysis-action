import datetime
import json
from collections.abc import Mapping
from pathlib import Path
from types import get_original_bases
from typing import Any, get_args, get_type_hints

import pytest
from githubkit import GitHub
from graphql import (
    GraphQLSchema,
    InputObjectTypeDefinitionNode,
    NamedTypeNode,
    NameNode,
    NonNullTypeNode,
    OperationDefinitionNode,
    build_ast_schema,
    parse,
    validate,
)
from respx import Route

from pyright_analysis_action._graphql import (
    GQLMutation,
    GQLPagedQuery,
    GQLQuery,
    GQLQueryBase,
    JSONAny,
    _unwrap_singles,
)

SCHEMA_FILE = Path(__file__).parent.parent / "github.schema.graphql"


@pytest.fixture(scope="session")
def github_graphql_schema() -> GraphQLSchema:
    schema_str = SCHEMA_FILE.read_text()
    graphql_ast = parse(schema_str)
    return build_ast_schema(graphql_ast, assume_valid=True)


@pytest.mark.parametrize(
    "input,drop,expected",
    (
        (42, (), 42),
        ({"foo": 42}, (), 42),
        ({"foo": 42, "bar": 17}, (), {"foo": 42, "bar": 17}),
        ({"foo": 42, "bar": 17}, ("bar",), 42),
        ({"foo": {"bar": [42], "spam": None}}, ("spam",), [42]),
    ),
)
def test_unwrap_singles(
    input: JSONAny, drop: tuple[str, ...], expected: JSONAny
) -> None:
    assert _unwrap_singles(input, *drop) == expected


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(qcls._query, id=qcls.__name__)
        for querycls in GQLQueryBase.__subclasses__()
        for qcls in querycls.__subclasses__()
    ],
)
def test_validate_graphql_query(
    github_graphql_schema: GraphQLSchema, query: str
) -> None:
    document = parse(query)
    errors = validate(github_graphql_schema, document)
    assert not errors


def _variables_types(
    query: type[GQLQueryBase[Mapping[str, Any], object]],
) -> dict[str, Any]:
    orig_base = get_original_bases(query)[0]
    variable_args, _ = get_args(orig_base)
    return get_type_hints(variable_args)


@pytest.mark.parametrize(
    "qcls, variable_types",
    [
        pytest.param(qcls, _variables_types(qcls), id=qcls.__name__)
        for querycls in GQLQueryBase.__subclasses__()
        for qcls in querycls.__subclasses__()
    ],
)
def test_validate_variables(
    github_graphql_schema: GraphQLSchema,
    qcls: type[GQLQuery] | type[GQLPagedQuery] | type[GQLMutation],
    variable_types: dict[str, Any],
) -> None:
    document = parse(qcls._query)
    op_def = document.definitions[0]
    assert isinstance(op_def, OperationDefinitionNode)

    # The names and types of the query input variables as defined in the query
    vdefs = [
        (vdef.variable.name.value, vdef.type) for vdef in op_def.variable_definitions
    ]
    # Mutations are special; they take an input type defined by the schema
    if issubclass(qcls, GQLMutation):
        _, input_type = vdefs[0]
        assert isinstance(input_type, NonNullTypeNode)
        input_type = input_type.type
        assert isinstance(input_type, NamedTypeNode)
        input_type_definition = github_graphql_schema.type_map[
            input_type.name.value
        ].ast_node
        assert isinstance(input_type_definition, InputObjectTypeDefinitionNode)
        vdefs = [(vdef.name.value, vdef.type) for vdef in input_type_definition.fields]

    handled: set[str] = set()
    for name, var_type in vdefs:
        match var_type:
            case NonNullTypeNode(type=NamedTypeNode(name=NameNode(value=type_name))):
                nullable = False
            case NamedTypeNode(name=NameNode(value=type_name)):
                nullable = True
            case _:
                raise AssertionError(f"Don't know how to process {var_type}")

        match type_name:
            case "ID" | "String":
                expected_type = str
            case "Int":
                expected_type = int
            case "DateTime":
                expected_type = datetime.datetime
            case _:
                raise AssertionError(f"Don't know how to validate {type_name}")

        if nullable:
            if name not in variable_types:
                continue
            expected_type = expected_type | None

        assert name in variable_types
        assert variable_types[name] == expected_type
        handled.add(name)

    # any input variable names in the typeddict that are not in the query?
    assert not variable_types.keys() - handled


async def test_qglquery(github: GitHub[Any], graphql_mock: Route) -> None:
    class TestQuery(GQLQuery[Any, Any]):
        _query = """query TestQuery() {}"""

    graphql_mock.respond(json={"data": {"foo": 42}})

    result = await TestQuery(github)({"foo": "bar"})
    assert result == 42
    req = graphql_mock.calls.last.request
    assert json.loads(req.content)["variables"] == {"foo": "bar"}


async def test_qglpagedquery(github: GitHub[Any], graphql_mock: Route) -> None:
    class TestQuery(GQLPagedQuery[Any, Any]):
        _query = "query TestQuery() {}"

    graphql_mock.respond(
        json={
            "data": {
                "foo": {
                    "nodes": [{"bar": 42}],
                    "pageInfo": {"hasNextPage": False, "endCursor": "foobar"},
                }
            }
        },
    )

    results = []
    async for page in TestQuery(github)({"foo": "bar"}):
        results.append(page)
    assert results == [[{"bar": 42}]]
    req = graphql_mock.calls.last.request
    assert json.loads(req.content)["variables"] == {"foo": "bar"}


async def test_qglmuttion(github: GitHub[Any], graphql_mock: Route) -> None:
    class TestQuery(GQLMutation[Any, Any]):
        _query = """mutation TestQuery() {}"""

    graphql_mock.respond(json={"data": {"foo": 42}})

    result = await TestQuery(github)({"foo": "bar"})
    assert result == 42
    req = graphql_mock.calls.last.request
    assert json.loads(req.content)["variables"] == {"input": {"foo": "bar"}}
