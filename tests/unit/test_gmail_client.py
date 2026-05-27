"""Unit tests for src.ingestion.gmail_client.

Tests cover:
    1. test_poll_gmail_first_run_baseline — first run returns ([], baseline_historyId)
    2. test_poll_gmail_history_returns_matching_messages — sender filtering works
    3. test_poll_gmail_history_404_fallback — historyId expiry triggers graceful recovery
    4. test_get_gmail_service_refreshes_expired_token — expired token is refreshed and saved
    5. test_fetch_message_body_extracts_plain_text — multipart body decoded correctly
"""

import base64
import builtins
import json
from io import StringIO
from unittest.mock import MagicMock, mock_open, patch

import pytest
from googleapiclient.errors import HttpError

from src.ingestion.gmail_client import (
    fetch_message_body,
    get_gmail_service,
    poll_gmail_since,
)

SENDER_FILTER = "jobalerts-noreply@linkedin.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_error(status: int, reason: str = "error") -> HttpError:
    """Create a googleapiclient.errors.HttpError with the given status code."""
    resp = MagicMock()
    resp.status = status
    resp.reason = reason
    return HttpError(resp=resp, content=b"error content")


def _build_mock_service() -> MagicMock:
    """Build a MagicMock that mimics the Gmail API resource chained call pattern."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Test 1: First-run baseline
# ---------------------------------------------------------------------------


def test_poll_gmail_first_run_baseline() -> None:
    """First run (start_history_id=None) returns ([], baseline_historyId)."""
    service = _build_mock_service()

    # messages().list().execute() returns a historyId and one message
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": "msg1"}],
        "historyId": "12345",
    }

    message_ids, history_id = poll_gmail_since(service, None, SENDER_FILTER)

    assert message_ids == []
    assert history_id == "12345"

    # Verify messages.list was called with the sender filter query
    service.users().messages().list.assert_called_with(
        userId="me", q=f"from:{SENDER_FILTER}", maxResults=1
    )


# ---------------------------------------------------------------------------
# Test 2: History poll with sender filtering
# ---------------------------------------------------------------------------


def test_poll_gmail_history_returns_matching_messages() -> None:
    """Only messages from sender_filter are returned; others are excluded."""
    service = _build_mock_service()

    # history().list().execute() returns two messageAdded events
    service.users().history().list().execute.return_value = {
        "history": [
            {
                "messagesAdded": [
                    {"message": {"id": "msg1"}},
                    {"message": {"id": "msg2"}},
                ]
            }
        ],
        "historyId": "20000",
    }

    # messages().get().execute() returns metadata — msg1 matches, msg2 does not
    def get_side_effect(userId, id, format, metadataHeaders):  # noqa: A002
        result = MagicMock()
        if id == "msg1":
            result.execute.return_value = {
                "payload": {
                    "headers": [
                        {"name": "From", "value": "LinkedIn <jobalerts-noreply@linkedin.com>"}
                    ]
                }
            }
        else:
            result.execute.return_value = {
                "payload": {
                    "headers": [
                        {"name": "From", "value": "someone@someother.com"}
                    ]
                }
            }
        return result

    service.users().messages().get.side_effect = get_side_effect

    message_ids, history_id = poll_gmail_since(service, "10000", SENDER_FILTER)

    assert message_ids == ["msg1"]
    assert history_id == "20000"


# ---------------------------------------------------------------------------
# Test 3: historyId 404 fallback
# ---------------------------------------------------------------------------


def test_poll_gmail_history_404_fallback() -> None:
    """When history.list() returns 404, falls back to messages.list baseline."""
    service = _build_mock_service()

    # history().list() raises HttpError 404 on first call (expired historyId)
    history_execute = MagicMock()
    history_execute.execute.side_effect = _make_http_error(404)
    service.users().history().list.return_value = history_execute

    # After 404, fallback to messages.list to get baseline historyId
    service.users().messages().list().execute.return_value = {
        "messages": [{"id": "baseline_msg"}],
        "historyId": "99999",
    }

    message_ids, history_id = poll_gmail_since(service, "OLD_EXPIRED_ID", SENDER_FILTER)

    assert message_ids == []
    assert history_id == "99999"


# ---------------------------------------------------------------------------
# Test 4: Token refresh on expired credentials
# ---------------------------------------------------------------------------


def test_get_gmail_service_refreshes_expired_token(tmp_path) -> None:
    """Expired credentials trigger refresh() and the token file is updated."""
    # Create a minimal fake token JSON
    token_data = {
        "token": "old_access_token",
        "refresh_token": "my_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }
    token_file = tmp_path / ".google_token.json"
    token_file.write_text(json.dumps(token_data))

    # Mock Credentials.from_authorized_user_file to return an expired creds object
    mock_creds = MagicMock()
    mock_creds.expired = True
    mock_creds.refresh_token = "my_refresh_token"
    mock_creds.to_json.return_value = json.dumps({**token_data, "token": "new_access_token"})

    with (
        patch(
            "src.ingestion.gmail_client.Credentials.from_authorized_user_file",
            return_value=mock_creds,
        ),
        patch("src.ingestion.gmail_client._refresh_credentials") as mock_refresh,
        patch("src.ingestion.gmail_client.build") as mock_build,
    ):
        get_gmail_service(str(token_file))

        # refresh() should have been called (via _refresh_credentials wrapper)
        mock_refresh.assert_called_once_with(mock_creds)

        # build() should be called to create the API resource
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)

        # The updated token should have been written back to the file
        written_content = token_file.read_text()
        assert "new_access_token" in written_content


# ---------------------------------------------------------------------------
# Test 5: fetch_message_body extracts plain text from multipart message
# ---------------------------------------------------------------------------


def test_fetch_message_body_extracts_plain_text() -> None:
    """fetch_message_body decodes base64url plain text and returns subject/sender."""
    service = _build_mock_service()

    plain_text = "Hello, this is the job alert body text."
    # Gmail uses URL-safe base64 without padding — encode the test body
    encoded_text = base64.urlsafe_b64encode(plain_text.encode("utf-8")).decode("ascii")

    service.users().messages().get().execute.return_value = {
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "Subject", "value": "Jobs for you"},
                {"name": "From", "value": "LinkedIn <jobalerts-noreply@linkedin.com>"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": encoded_text},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(b"<p>HTML body</p>").decode()},
                },
            ],
        }
    }

    result = fetch_message_body(service, "test_msg_id")

    assert result["body_text"] == plain_text
    assert result["subject"] == "Jobs for you"
    assert result["sender"] == "LinkedIn <jobalerts-noreply@linkedin.com>"
