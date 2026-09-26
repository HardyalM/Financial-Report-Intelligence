"""Test-wide guards.

Network access is disabled for every test (CLAUDE.md: "No live network in unit tests").
A test may opt out only with the `network` marker, which the default CI run never selects.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any, NoReturn

import pytest


class NetworkBlockedError(RuntimeError):
    """Raised when a unit test tries to reach the network."""


def _blocked(*_args: Any, **_kwargs: Any) -> NoReturn:
    raise NetworkBlockedError("network access is disabled in unit tests (see tests/conftest.py)")


@pytest.fixture(autouse=True)
def _no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("network") is None:
        monkeypatch.setattr(socket.socket, "connect", _blocked)
        monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
        monkeypatch.setattr(socket, "create_connection", _blocked)
        monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    yield
