from collections.abc import AsyncIterable

import pytest
import respx
from githubkit import GitHub


@pytest.fixture
def pyright_json_report() -> str:
    return r"""
{
    "version": "1.1.391",
    "time": "1735043053980",
    "generalDiagnostics": [],
    "summary": {
        "filesAnalyzed": 376,
        "errorCount": 0,
        "warningCount": 0,
        "informationCount": 0,
        "timeInSec": 5.506
    },
    "typeCompleteness": {
        "packageName": "foobar",
        "moduleName": "foobar",
        "ignoreUnknownTypesFromImports": true,
        "exportedSymbolCounts": {
            "withKnownType": 9794,
            "withAmbiguousType": 852,
            "withUnknownType": 1599
        },
        "otherSymbolCounts": {
            "withKnownType": 90,
            "withAmbiguousType": 3,
            "withUnknownType": 16
        },
        "missingFunctionDocStringCount": 1087,
        "missingClassDocStringCount": 327,
        "missingDefaultParamCount": 0,
        "completenessScore": 0.7998366680277664,
        "modules": [
            {"name": "foobar"},
            {"name": "foobar.ham"},
            {"name": "foobar.spam"},            
            {"name": "foobar.spam.vikings"}
        ],
        "symbols": [
            {
                "category": "module",
                "name": "foobar.ham",
                "referenceCount": 1,
                "isExported": true,
                "isTypeKnown": true,
                "isTypeAmbiguous": false,
                "diagnostics": []
            },
            {
                "category": "class",
                "name": "foobar.MontyPython",
                "referenceCount": 1,
                "isExported": true,
                "isTypeKnown": false,
                "isTypeAmbiguous": false,
                "diagnostics": []
            },
            {
                "category": "function",
                "name": "foobar._private_function",
                "referenceCount": 1,
                "isExported": false,
                "isTypeKnown": false,
                "isTypeAmbiguous": false,
                "diagnostics": []
            },
            {
                "category": "method",
                "name": "foobar.MontyPython.__init__",
                "referenceCount": 1,
                "isExported": true,
                "isTypeKnown": false,
                "isTypeAmbiguous": false,
                "diagnostics": [
                    {
                        "file": "/.../foobar/__init__.py",
                        "severity": "error",
                        "message": "Type of parameter \"first_name\" is partially unknown\nParameter type is \"type[NameString]\"",
                        "range": {
                            "start": {
                                "line": 180,
                                "character": 8
                            },
                            "end": {
                                "line": 180,
                                "character": 16
                            }
                        }
                    },
                    {
                        "file": "/.../foobar/__init__.py",
                        "severity": "error",
                        "message": "Type of parameter \"last_name\" is partially unknown\n\u00a0\u00a0Parameter type is \"type[NameString]\"",
                        "range": {
                            "start": {
                                "line": 180,
                                "character": 8
                            },
                            "end": {
                                "line": 180,
                                "character": 16
                            }
                        }
                    }
                ]
            }
        ]
    }
}
"""


@pytest.fixture
async def github() -> AsyncIterable[GitHub]:
    async with GitHub("mocked_auth") as client:
        yield client


@pytest.fixture
def graphql_mock(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.post(url="https://api.github.com/graphql", name="graphql")
