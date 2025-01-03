import asyncio
import base64
import datetime
import logging
import os
import types
from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from itertools import count
from typing import Annotated, Self

import aiohttp
import typer
from aiohttp import hdrs
from humanize import naturalsize
from pydantic import BaseModel
from pydantic.networks import AnyHttpUrl
from pydantic.types import AwareDatetime
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)
from yarl import URL

# smokeshow asks for a key where the first 22 bits of the SHA256 hash are 0.
# This translates to a digest with 2 NULs and a 0, 1, 2 or 3 byte in position 3
HASH_PREFIXES = tuple(bytes([0, 0, i]) for i in range(4))
REPORT_INTERVAL = 100_000


USER_AGENT = (
    "pyright-analysis-action/{version} "
    "(https://github.com/mjpieters/pyright-analysis-action)"
)
SMOKESHOW_CREATE = URL("https://smokeshow.helpmanual.io/create/")
AUTHORIZATION_HDR = "Authorisation"  # Smokeshow misspells the header (UK sp.)

_logger = logging.getLogger(__name__)


def _is_server_error(exception: BaseException) -> bool:
    if isinstance(exception, aiohttp.ClientConnectionError | asyncio.TimeoutError):
        return True
    return (
        isinstance(exception, aiohttp.ClientResponseError)
        and exception.status // 100 == 5
    )


# Retry on timeout, connection error or a 5xx response, up to 3 times, with
# exponential back-off between 0.1 and 10 seconds, with random jitter injected.
_smokeshow_retry = retry(
    retry=retry_if_exception(_is_server_error),
    before_sleep=before_sleep_log(_logger, logging.WARNING),
    wait=wait_exponential_jitter(initial=0.1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)


class SmokeshowCreateResponse(BaseModel):
    message: str
    secret_key: str
    site_creation: AwareDatetime
    site_expiration: AwareDatetime
    sites_created_24h: int
    upload_expiration: AwareDatetime
    url: Annotated[str, AnyHttpUrl]

    def __str__(self) -> str:
        lines = [
            self.message,
            f"    created at:          {self.site_creation.isoformat(timespec="seconds")}",
            f"    expires at:          {self.site_expiration.isoformat(timespec="seconds")}",
            f"    sites created (24h): {self.sites_created_24h}",
            f"    upload to:           {self.url}",
        ]
        return "\n".join(lines)


class SmokeshowUploadResponse(BaseModel):
    path: str
    content_type: str
    size: int
    total_site_size: int

    def __str__(self) -> str:
        size, total = (
            naturalsize(self.size, True),
            naturalsize(self.total_site_size, True),
        )
        return f"Uploaded {self.path} ({self.content_type}, {size}, total {total})"


def generate_smokeshow_key() -> str:
    typer.echo(
        "Generating a smokeshow key with valid hash. Hold tight, this might take a minute..."
    )
    attempt, attempts = count(1).__next__, 0
    hash = seed = b""
    while not hash.startswith(HASH_PREFIXES):  # pragma: no cover
        if not (attempts := attempt()) % REPORT_INTERVAL:
            typer.echo(".", nl=False)
        seed = os.urandom(50)
        hash = sha256(seed).digest()

    typer.echo(f"\nSuccess! Key found after {attempts:,} attempts.")
    return base64.b64encode(seed).decode().rstrip("=")


class SmokeshowSite(AbstractAsyncContextManager["SmokeshowSite"]):
    def __init__(self, key: str | None = None) -> None:
        self._key = key

    @property
    def expiration(self) -> datetime.datetime:
        return self._create_response.site_expiration

    async def __aenter__(self) -> Self:
        from . import __version__

        self._client = await aiohttp.ClientSession(
            headers={hdrs.USER_AGENT: USER_AGENT.format(version=__version__)}
        ).__aenter__()
        self._create_response = await self.create_site()
        typer.echo(self._create_response)
        self._client.headers[AUTHORIZATION_HDR] = self._create_response.secret_key
        setattr(self._client, "_base_url", URL(self._create_response.url))
        return self

    @_smokeshow_retry
    async def create_site(self) -> SmokeshowCreateResponse:
        key = self._key
        if key is None:
            key = generate_smokeshow_key()
        async with self._client.post(
            SMOKESHOW_CREATE, headers={AUTHORIZATION_HDR: key}
        ) as response:
            response.raise_for_status()
            return SmokeshowCreateResponse.model_validate_json(await response.read())

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> bool | None:
        return await self._client.__aexit__(exc_type, exc_value, traceback)

    @_smokeshow_retry
    async def upload(self, name: str, data: bytes, content_type: str) -> URL:
        async with self._client.post(
            name, headers={hdrs.CONTENT_TYPE: content_type}, data=data
        ) as response:
            response.raise_for_status()
            upload_info = SmokeshowUploadResponse.model_validate_json(
                await response.read()
            )
        typer.secho(upload_info, italic=True)
        return response.url


async def upload(
    key: str | None, html_page: str, preview_image: bytes
) -> tuple[datetime.datetime, URL, URL]:
    async with SmokeshowSite(key) as site:
        async with asyncio.TaskGroup() as group:
            html_task = group.create_task(
                site.upload("index.html", html_page.encode(), "text/html"),
                name="html_upload",
            )
            image_task = group.create_task(
                site.upload("preview.svg", preview_image, "image/svg+xml"),
                name="preview_upload",
            )
        html_url = html_task.result()
        if html_url.parts[-1] == "index.html":  # pragma: no cover
            html_url = html_url.parent
        image_url = image_task.result()
        return site.expiration, html_url, image_url
