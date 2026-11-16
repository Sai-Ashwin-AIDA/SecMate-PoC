"""Explicit pytest plugin for offline worker verification; not auto-loaded by product."""
import socket
import threading

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    original_connect = socket.socket.connect
    original_pair = socket.socketpair
    local = threading.local()

    def denied(*args, **kwargs):
        raise AssertionError("Offline verification forbids network access")

    def connect(sock, address):
        # CPython on Windows implements socketpair with a private ephemeral
        # loopback pair. Permit ONLY that stdlib operation for asyncio's wakeup
        # pipe, never arbitrary localhost/product/provider connections.
        if getattr(local, "stdlib_pair", False) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        return denied()

    def socketpair(*args, **kwargs):
        local.stdlib_pair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            local.stdlib_pair = False

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "socketpair", socketpair)
