"""Gmail API client: OAuth2 authentication, historyId-based polling, and message body fetching.

Exports:
    get_gmail_service: Load OAuth2 credentials and return a Gmail API resource.
    poll_gmail_since: Poll for new messages since a given historyId, filtered by sender.
    fetch_message_body: Fetch and decode the plain-text body of a Gmail message.
"""

import base64

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import retry, stop_after_attempt, wait_exponential

log = structlog.get_logger()

# Gmail OAuth2 scope — read-only is sufficient for polling and fetching bodies
_GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _refresh_credentials(creds: Credentials) -> None:
    """Refresh expired OAuth2 credentials with tenacity retry on transient errors."""
    creds.refresh(Request())


def get_gmail_service(token_path: str):  # type: ignore[return]
    """Load OAuth2 credentials from token_path and return a Gmail API resource.

    If the credentials are expired and a refresh_token is available, the token is
    refreshed automatically and the updated credentials are written back to token_path.
    Uses tenacity @retry around the refresh call to handle transient network errors.

    Args:
        token_path: Path to the OAuth2 token JSON file (e.g. .google_token.json).

    Returns:
        A Google API resource object for the Gmail v1 API.
    """
    creds = Credentials.from_authorized_user_file(token_path)

    if creds.expired and creds.refresh_token:
        log.info("gmail_token_refresh_start", token_path=token_path)
        _refresh_credentials(creds)
        # Write the refreshed token back to disk so the next run uses the new access token
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        log.info("gmail_token_refreshed", token_path=token_path)

    return build("gmail", "v1", credentials=creds)


def poll_gmail_since(
    service,
    start_history_id: str | None,
    sender_filter: str,
) -> tuple[list[str], str]:
    """Poll Gmail for new messages since start_history_id, filtered by sender.

    If start_history_id is None (first run), establishes a baseline historyId from
    the most recent message matching sender_filter and returns an empty list — no
    messages are returned on the first run.

    If start_history_id is provided, fetches all messageAdded events since that
    historyId, fetches each message's From header, and returns only the IDs of
    messages where sender_filter appears in the From header.

    On Gmail API HTTP 404 (historyId expired), falls back gracefully per Pitfall 1:
    logs a warning, resets baseline from messages.list, and returns an empty list
    with the new baseline historyId.

    Args:
        service: Gmail API resource (from get_gmail_service).
        start_history_id: Checkpoint historyId from last poll, or None on first run.
        sender_filter: Sender email address to filter by (e.g. jobalerts-noreply@linkedin.com).

    Returns:
        Tuple of (matching_message_ids, new_history_id).
        matching_message_ids is empty on first run or when historyId is reset.
    """
    if start_history_id is None:
        # First run — establish baseline historyId from the most recent matching message
        log.info("gmail_first_run_baseline", sender_filter=sender_filter)
        result = (
            service.users()
            .messages()
            .list(userId="me", q=f"from:{sender_filter}", maxResults=1)
            .execute()
        )
        # historyId from messages.list is the current mailbox historyId
        baseline_history_id = result.get("historyId", "1")
        log.info("gmail_baseline_established", history_id=baseline_history_id)
        return [], baseline_history_id

    # Normal poll — fetch history since start_history_id
    all_message_ids: list[str] = []
    latest_history_id = start_history_id
    page_token = None

    try:
        while True:
            kwargs: dict = {
                "userId": "me",
                "startHistoryId": start_history_id,
                "historyTypes": ["messageAdded"],
            }
            if page_token:
                kwargs["pageToken"] = page_token

            response = service.users().history().list(**kwargs).execute()

            latest_history_id = response.get("historyId", latest_history_id)

            for record in response.get("history", []):
                for msg in record.get("messagesAdded", []):
                    all_message_ids.append(msg["message"]["id"])

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    except HttpError as exc:
        if exc.resp.status == 404:
            # historyId has expired — reset baseline per RESEARCH.md Pitfall 1
            log.warning(
                "gmail_history_id_expired",
                start_history_id=start_history_id,
                detail=str(exc),
            )
            return poll_gmail_since(service, None, sender_filter)
        raise

    log.info(
        "gmail_history_polled",
        raw_count=len(all_message_ids),
        new_history_id=latest_history_id,
    )

    if not all_message_ids:
        return [], latest_history_id

    # Filter messages by sender — history.list doesn't support sender filtering directly
    matching_ids: list[str] = []
    for msg_id in all_message_ids:
        msg_meta = (
            service.users()
            .messages()
            .get(userId="me", id=msg_id, format="metadata", metadataHeaders=["From"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in msg_meta.get("payload", {}).get("headers", [])}
        if sender_filter in headers.get("From", ""):
            matching_ids.append(msg_id)

    log.info(
        "gmail_messages_filtered",
        matching_count=len(matching_ids),
        sender_filter=sender_filter,
        new_history_id=latest_history_id,
    )
    return matching_ids, latest_history_id


def fetch_message_body(service, message_id: str) -> dict:
    """Fetch a Gmail message and extract its plain-text body, subject, and sender.

    For multipart messages, iterates MIME parts to find text/plain. Base64url-decodes
    the body data. Also extracts Subject and From headers.

    Args:
        service: Gmail API resource (from get_gmail_service).
        message_id: The Gmail message ID to fetch.

    Returns:
        Dict with keys: body_text (str), subject (str | None), sender (str | None).
    """
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    payload = message.get("payload", {})

    # Extract Subject and From headers
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
    subject = headers.get("Subject")
    sender = headers.get("From")

    # Extract plain-text body from MIME payload
    body_text = _extract_plain_text(payload)

    log.info(
        "gmail_message_fetched",
        message_id=message_id,
        subject=subject,
        body_length=len(body_text),
    )

    return {
        "body_text": body_text,
        "subject": subject,
        "sender": sender,
    }


def resolve_apply_type(url: str) -> str:
    """Resolve apply_type from a job URL string.

    Returns 'linkedin_easy_apply' when the URL contains 'linkedin.com',
    otherwise returns 'email' (the default apply type for email-sourced jobs).

    Args:
        url: The job application URL extracted from the email or workflow.

    Returns:
        'linkedin_easy_apply' for LinkedIn URLs, 'email' for all others.
    """
    return "linkedin_easy_apply" if "linkedin.com" in url.lower() else "email"


def _extract_plain_text(payload: dict) -> str:
    """Recursively extract text/plain body from a MIME payload dict.

    Handles both single-part and multipart messages. Returns an empty string
    if no text/plain part is found.
    """
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        body_data = payload.get("body", {}).get("data", "")
        if body_data:
            # Gmail uses base64url encoding (URL-safe base64 without padding)
            return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        return ""

    # For multipart messages, search all parts recursively
    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_plain_text(part)
            if text:
                return text

    return ""
