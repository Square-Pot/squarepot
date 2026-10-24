# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backing off clients that keep sending a wrong API token."""

from __future__ import annotations

import logging
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from squarepot_server.backoff import Backoff
from tests.conftest import TOKEN, runtime


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(client: TestClient) -> Clock:
    fake = Clock()
    runtime(client).backoff = Backoff(clock=fake)
    return fake


def get(client: TestClient, token: str | None, **headers: str) -> int:
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    response = client.get("/api/v1/collections", headers=headers)
    return response.status_code


def test_ten_wrong_tokens_then_the_client_must_wait(
    client: TestClient, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    client.headers.pop("Authorization")
    assert get(client, TOKEN) == 200
    with caplog.at_level(logging.WARNING):
        assert [get(client, "wrong") for _ in range(9)] == [401] * 9
        assert get(client, None) == 401
    assert "too many wrong API tokens" in caplog.text
    assert TOKEN not in caplog.text
    # Blocked now, even with the right token, which is not checked.
    response = client.get("/api/v1/collections", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json()["code"] == "too_many_requests"
    assert client.get("/api/v1/health").status_code == 200
    # One attempt comes back each minute.
    clock.now = 59
    assert get(client, TOKEN) == 429
    clock.now = 60
    assert get(client, "wrong") == 401
    assert get(client, TOKEN) == 429
    clock.now = 120
    assert get(client, TOKEN) == 200


def test_the_right_token_uses_no_attempts(client: TestClient, clock: Clock) -> None:
    assert [get(client, TOKEN) for _ in range(30)] == [200] * 30


def test_clients_are_told_apart_by_the_address_a_trusted_proxy_forwards(
    client: TestClient, clock: Clock
) -> None:
    # uvicorn and Starlette type the same ASGI interface each their own way.
    app = ProxyHeadersMiddleware(cast(Any, client.app), trusted_hosts="testclient")
    proxied = TestClient(cast(Any, app))
    for _ in range(10):
        assert get(proxied, "wrong", **{"X-Forwarded-For": "203.0.113.7"}) == 401
    assert get(proxied, TOKEN, **{"X-Forwarded-For": "203.0.113.7"}) == 429
    assert get(proxied, TOKEN, **{"X-Forwarded-For": "198.51.100.2"}) == 200
    # Without a trusted proxy, the header is ignored: this client is "testclient".
    assert get(client, TOKEN, **{"X-Forwarded-For": "203.0.113.7"}) == 200


def test_the_oldest_clients_are_forgotten_first() -> None:
    backoff = Backoff(capacity=2, max_clients=3, clock=Clock())
    for client in ["a", "b", "c", "d"]:
        backoff.fail(client)
    assert list(backoff.buckets) == ["b", "c", "d"]
    assert backoff.fail("b")
    assert backoff.retry_after("b") == 60
    assert backoff.retry_after("a") is None
