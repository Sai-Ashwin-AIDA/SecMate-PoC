"""Offline isolation is installed during collection, before application imports."""

import os
import socket
import threading
from pathlib import Path

import pytest

# Never load a .env; remove inherited provider/tracing credentials from this process.
for name in list(os.environ):
    if name.startswith(("OPENROUTER_", "LANGSMITH_", "LANGCHAIN_")):
        os.environ.pop(name)
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"


def deny_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("Network access to external endpoints is prohibited in offline tests.")


# Block DNS and outbound connections, including during test-module imports.
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_pair = socket.socketpair
_pair_state = threading.local()


def guarded_connect(stream, address):
    if getattr(_pair_state, "creating", False):
        return _original_connect(stream, address)
    return deny_network()


def guarded_connect_ex(stream, address):
    if getattr(_pair_state, "creating", False):
        return _original_connect_ex(stream, address)
    return deny_network()


def internal_socketpair(*args, **kwargs):
    # User-approved Windows asyncio wake-up pair only. The narrow thread-local
    # exception exists during socketpair construction, never during model calls.
    _pair_state.creating = True
    try:
        return _original_pair(*args, **kwargs)
    finally:
        _pair_state.creating = False


socket.socket.connect = guarded_connect
socket.socket.connect_ex = guarded_connect_ex
socket.socketpair = internal_socketpair
socket.socket.sendto = deny_network
socket.create_connection = deny_network
socket.getaddrinfo = deny_network
socket.gethostbyname = deny_network
socket.gethostbyname_ex = deny_network
socket.gethostbyaddr = deny_network


@pytest.fixture(autouse=True)
def offline_tracing():
    from langsmith import tracing_context

    with tracing_context(enabled=False):
        yield


@pytest.fixture
def roots(tmp_path: Path):
    from local_document_agent.filesystem import FilesystemRoots

    source = tmp_path / "input"
    destination = tmp_path / "output"
    source.mkdir()
    destination.mkdir()
    return FilesystemRoots(source, destination)


@pytest.fixture
def kit(roots):
    from local_document_agent.context import ToolContext
    from local_document_agent.tools import build_tools

    context = ToolContext()
    return {item.name: item for item in build_tools(roots, context)}, context
