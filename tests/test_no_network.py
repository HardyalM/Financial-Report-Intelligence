"""Gate item: opening a network connection inside a unit test must fail."""

from __future__ import annotations

import socket

import pytest

from tests.conftest import NetworkBlockedError


def test_create_connection_is_blocked() -> None:
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("example.com", 443), timeout=1)


def test_raw_socket_connect_is_blocked() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock,
        pytest.raises(NetworkBlockedError),
    ):
        sock.connect(("93.184.216.34", 80))


def test_dns_lookup_is_blocked() -> None:
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.com", 443)
