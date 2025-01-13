import datetime
from collections.abc import Iterator
from io import StringIO
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
import typer
from yarl import URL

from pyright_analysis_action.action import action
from pyright_analysis_action.comment import NotCommenting


class TestAction:
    upload_result = (
        datetime.datetime.now(tz=datetime.UTC),
        URL("http://example.com/foobar"),
        URL("http://example.com/foobar/preview.svg"),
    )

    @pytest.fixture(autouse=True)
    def _setup(self, pyright_json_report: str) -> Iterator[None]:
        self.report = cast(typer.FileText, StringIO(pyright_json_report))
        with (
            patch(
                "pyright_analysis.treemap.to_treemap", autospec=True
            ) as self.mock_to_treemap,
            patch(
                "pyright_analysis_action.action.upload", autospec=True
            ) as self.mock_upload,
            patch(
                "pyright_analysis_action.action.set_outputs", autospec=True
            ) as self.mock_set_outputs,
        ):
            figure: MagicMock = self.mock_to_treemap.return_value
            self.mock_to_html: MagicMock = figure.to_html
            self.mock_to_html.return_value = "<html/>"
            self.mock_to_image: MagicMock = figure.to_image
            self.mock_to_image.return_value = b"<svg/>"
            self.mock_upload.return_value = self.upload_result
            yield

    @pytest.mark.parametrize("div_id", (None, "some-div-id"))
    def test_html_args_passthrough(self, div_id: str | None) -> None:
        action(self.report, div_id=div_id)
        self.mock_to_html.assert_called_once_with(div_id=div_id, include_plotlyjs="cdn")

    @pytest.mark.parametrize("smokeshow_auth_key", (None, "some-test-value"))
    def test_upload_key_passthrough(self, smokeshow_auth_key: str | None) -> None:
        action(self.report, smokeshow_auth_key=smokeshow_auth_key)
        self.mock_upload.assert_called_once_with(
            smokeshow_auth_key, "<html/>", b"<svg/>"
        )

    def test_outputs_set(self):
        output = MagicMock()
        action(self.report, output=output)
        expiration, html_url, preview_url = self.upload_result
        self.mock_set_outputs.assert_called_once_with(
            output,
            html_url=html_url,
            preview_url=preview_url,
            expiration=expiration.isoformat(),
            comment_url=None,
        )

    def test_not_commenting(self) -> None:
        with (
            patch(
                "pyright_analysis_action.comment.Commenter.from_event",
                autospec=True,
                side_effect=NotCommenting("mocked"),
            ),
            patch("typer.secho", autospec=True) as mock_secho,
        ):
            action(
                self.report,
                comment_on_pr=True,
                event_name="some_event",
                event_file=MagicMock(),
            )
        mock_secho.assert_any_call("Skipping posting a PR comment: mocked", dim=True)

    def test_commenting(self) -> None:
        output = MagicMock()
        with (
            patch(
                "pyright_analysis_action.action.Commenter",
                autospec=True,
                side_effect=NotCommenting("mocked"),
            ) as mocked_commenter,
            patch("typer.secho", autospec=True) as mock_secho,
        ):
            post_call = mocked_commenter.from_event.return_value.post_or_update_comment
            post_call.return_value = "http://example.com/"
            action(
                self.report,
                comment_on_pr=True,
                event_name="some_event",
                event_file=MagicMock(),
                output=output,
            )
        mock_secho.assert_any_call("Comment posted or updated at http://example.com/")
        expiration, html_url, preview_url = self.upload_result
        self.mock_set_outputs.assert_called_once_with(
            output,
            html_url=html_url,
            preview_url=preview_url,
            expiration=expiration.isoformat(),
            comment_url="http://example.com/",
        )
