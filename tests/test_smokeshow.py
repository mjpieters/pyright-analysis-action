import asyncio
import datetime
from collections.abc import Iterator
from typing import Protocol
from unittest.mock import Mock, patch, seal

import pytest
from aiohttp import (
    ClientConnectionError,
    ClientResponse,
    hdrs,
)
from aioresponses import aioresponses as AioResponses
from yarl import URL

from pyright_analysis_action import __version__
from pyright_analysis_action.smokeshow import (
    SMOKESHOW_CREATE,
    USER_AGENT,
    SmokeshowCreateResponse,
    SmokeshowUploadResponse,
    generate_smokeshow_key,
    upload,
)

_STREAM_WRITER = Mock(output_size=0)
seal(_STREAM_WRITER)


@pytest.fixture(autouse=True)
def patch_aiohttp() -> Iterator[None]:
    # Work around pnuckowski/aioresponses#289, caused by an API change in
    # aiohttp 3.14.0. This provides the missing keyword argument as a mock,
    # which suffices for these tests. This is what the upstream patch
    # at pnuckowski/aioresponses#288 does. On future versions of aioresponses
    # this patch should be a noop.

    patched_init = orig_init = ClientResponse.__init__
    if "stream_writer" in orig_init.__annotations__:

        def patched_init(self, *args, **kwargs) -> None:
            orig_init(self, *args, **({"stream_writer": _STREAM_WRITER} | kwargs))

    ClientResponse.__init__ = patched_init
    try:
        yield
    finally:
        ClientResponse.__init__ = orig_init


@pytest.fixture
def aioresponses() -> Iterator[AioResponses]:
    with AioResponses() as m:
        yield m


@pytest.fixture
def secret_key() -> str:
    return "not-so-secret-or-random-fake-value"


@pytest.fixture
def create_response(aioresponses: AioResponses, secret_key: str) -> None:
    base = datetime.datetime.now(datetime.UTC)
    response = SmokeshowCreateResponse(
        message="Test site creation mocked",
        secret_key=secret_key,
        site_creation=base,
        site_expiration=base + datetime.timedelta(days=365),
        sites_created_24h=17,
        upload_expiration=base + datetime.timedelta(minutes=5),
        url="https://test.example.com/foobar/",
    )
    aioresponses.post(SMOKESHOW_CREATE, status=200, body=response.model_dump_json())


class UploadResponseFactory(Protocol):
    def __call__(self, path: str) -> None: ...


@pytest.fixture
def upload_response_factory(aioresponses: AioResponses) -> UploadResponseFactory:
    def upload_response(path: str) -> None:
        response = SmokeshowUploadResponse(
            path=path,
            content_type="example/mock-type",
            size=1234,
            total_site_size=123456,
        )
        aioresponses.post(
            f"https://test.example.com/foobar/{path}",
            status=200,
            body=response.model_dump_json(),
        )

    return upload_response


@patch(
    "pyright_analysis_action.smokeshow.HASH_PREFIXES",
    new=tuple(bytes([0, 0, i]) for i in range(32)),
)
def test_generate_smokeshow_key() -> None:
    result = generate_smokeshow_key()
    assert isinstance(result, str)


class TestSmokeshowUpload:
    @pytest.fixture(autouse=True)
    def _setup(self) -> Iterator[None]:
        with patch(
            "pyright_analysis_action.smokeshow.generate_smokeshow_key",
            autospec=True,
        ) as self.mock_generate_key:
            yield

    @pytest.mark.parametrize("smokeshow_key", (None, "provided-key"))
    @pytest.mark.usefixtures("create_response")
    def test_upload(
        self,
        aioresponses: AioResponses,
        upload_response_factory: UploadResponseFactory,
        smokeshow_key: str | None,
        secret_key: str,
    ) -> None:
        self.mock_generate_key.return_value = "random-generated-test-key"
        upload_response_factory("index.html")
        upload_response_factory("preview.svg")
        result = asyncio.run(upload(smokeshow_key, "<html/>", b"<svg/>"))
        if not smokeshow_key:
            self.mock_generate_key.assert_any_call()
        else:
            assert not self.mock_generate_key.called
        expected_authorization = smokeshow_key or "random-generated-test-key"
        base_headers = {"User-Agent": USER_AGENT.format(version=__version__)}
        aioresponses.assert_called_with(
            SMOKESHOW_CREATE,
            hdrs.METH_POST,
            headers=base_headers | {"Authorisation": expected_authorization},
        )
        aioresponses.assert_called_with(
            "https://test.example.com/foobar/index.html",
            hdrs.METH_POST,
            headers=base_headers
            | {"Authorisation": secret_key, hdrs.CONTENT_TYPE: "text/html"},
            data=b"<html/>",
            allow_redirects=True,
        )
        aioresponses.assert_called_with(
            "https://test.example.com/foobar/preview.svg",
            hdrs.METH_POST,
            headers=base_headers
            | {"Authorisation": secret_key, hdrs.CONTENT_TYPE: "image/svg+xml"},
            data=b"<svg/>",
            allow_redirects=True,
        )

        assert result[1] == URL("https://test.example.com/foobar")
        assert result[2] == URL("https://test.example.com/foobar/preview.svg")

    @pytest.mark.parametrize(
        "exception_or_status",
        (TimeoutError(), ClientConnectionError(), 500),
    )
    def test_upload_retries(
        self,
        request: pytest.FixtureRequest,
        aioresponses: AioResponses,
        upload_response_factory: UploadResponseFactory,
        exception_or_status: Exception,
    ) -> None:
        self.mock_generate_key.return_value = "random-generated-test-key"

        if isinstance(exception_or_status, int):
            exception, status = None, exception_or_status
        else:
            exception, status = exception_or_status, None

        # set up exceptions per endpoint
        aioresponses.post(SMOKESHOW_CREATE, status=status, exception=exception)
        request.getfixturevalue("create_response")

        aioresponses.post(
            "https://test.example.com/foobar/index.html",
            status=status,
            exception=exception,
        )
        upload_response_factory("index.html")

        aioresponses.post(
            "https://test.example.com/foobar/preview.svg",
            status=status,
            exception=exception,
        )
        upload_response_factory("preview.svg")

        # when retrying, don't _actually_ wait.
        with patch("tenacity.wait.wait_exponential_jitter.__call__", return_value=0.0):
            result = asyncio.run(upload(None, "<html/>", b"<svg/>"))

        assert result[1] == URL("https://test.example.com/foobar")
        assert result[2] == URL("https://test.example.com/foobar/preview.svg")
