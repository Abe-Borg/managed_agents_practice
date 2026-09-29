from __future__ import annotations

import httpx2
from anthropic import AuthenticationError, RateLimitError

from csv_analyst.platform import PlatformArchivedAgent, user_facing_error


def _response(status: int, **headers: str) -> httpx2.Response:
    return httpx2.Response(
        status,
        headers=headers,
        request=httpx2.Request("GET", "https://api.anthropic.com/v1/sessions"),
    )


def test_api_errors_are_actionable_without_raw_response_body() -> None:
    secret = "fake-secret-value"
    auth = AuthenticationError(secret, response=_response(401), body=None)
    with_retry = RateLimitError(
        secret, response=_response(429, **{"retry-after": "3"}), body=None
    )
    spend_cap = RateLimitError(secret, response=_response(429), body=None)

    assert "ANTHROPIC_API_KEY" in user_facing_error(auth)
    assert "Retry after 3 seconds" in user_facing_error(with_retry)
    assert "spend cap" in user_facing_error(spend_cap)
    assert "setup" in user_facing_error(PlatformArchivedAgent("Re-run setup"))
    assert all(
        secret not in user_facing_error(error)
        for error in (auth, with_retry, spend_cap)
    )
