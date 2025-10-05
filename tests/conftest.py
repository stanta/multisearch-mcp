import importlib
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Type

import anyio
import pytest
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from ddgs.exceptions import DDGSException, TimeoutException
from mcp.client.session import ClientSession
from mcp.server.lowlevel.server import NotificationOptions
from mcp.shared.message import SessionMessage

# -------------------------------
# Test constants and result factory
# -------------------------------

CATEGORIES = ["text", "images", "news", "videos", "books"]


def fake_results(category: str, n: Optional[int]) -> List[Dict[str, Any]]:
    """
    Produce deterministic, category-appropriate fake result dicts.

    Categories and minimal fields:
      - text:   {title, href, body}
      - images: {title, image, thumbnail, url}
      - news:   {title, href, body, source, date}
      - videos: {title, url, content, source}
      - books:  {title, url, authors, published}
    """
    count = 5 if n is None else int(n)
    items: List[Dict[str, Any]] = []
    if category == "text":
        for i in range(count):
            items.append(
                {
                    "title": f"Text Result {i}",
                    "href": f"https://example.com/text/{i}",
                    "body": f"Body {i}",
                }
            )
        return items
    if category == "images":
        for i in range(count):
            items.append(
                {
                    "title": f"Image Result {i}",
                    "image": f"https://img.example.com/full/{i}.jpg",
                    "thumbnail": f"https://img.example.com/thumb/{i}.jpg",
                    "url": f"https://example.com/images/{i}",
                }
            )
        return items
    if category == "news":
        for i in range(count):
            items.append(
                {
                    "title": f"News Result {i}",
                    "href": f"https://example.com/news/{i}",
                    "body": f"News body {i}",
                    "source": "Example Times",
                    "date": f"2025-01-{(i % 28) + 1:02d}",
                }
            )
        return items
    if category == "videos":
        for i in range(count):
            items.append(
                {
                    "title": f"Video Result {i}",
                    "url": f"https://video.example.com/watch?v={i}",
                    "content": f"Video content {i}",
                    "source": "ExampleTube",
                }
            )
        return items
    if category == "books":
        for i in range(count):
            items.append(
                {
                    "title": f"Book Result {i}",
                    "url": f"https://books.example.com/{i}",
                    "authors": [f"Author {i}"],
                    "published": f"20{10 + (i % 15)}",
                }
            )
        return items
    raise ValueError(f"Unknown category for fake results: {category}")


# -------------------------------
# Fake DDGS engines
# -------------------------------

class _BaseFakeDDGS:
    """
    Base fake DDGS that records last calls and supports `with DDGS() as ddgs:` usage.
    """
    last_instance: Optional["_BaseFakeDDGS"] = None
    call_count: int = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.last_calls: Dict[str, Dict[str, Any]] = {}
        type(self).last_instance = self  # store class-level pointer to latest instance

    # Support usage as a context manager: with DDGS() as d:
    def __enter__(self) -> "_BaseFakeDDGS":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def _record(self, category: str, **kwargs: Any) -> None:
        self.last_calls[category] = kwargs
        type(self).call_count += 1


class SuccessFakeDDGS(_BaseFakeDDGS):
    """
    Fake that returns deterministic lists according to category and max_results.
    It also captures the forwarded arguments for verification.
    """

    def text(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._record("text", keywords=keywords, **kwargs)
        return fake_results("text", kwargs.get("max_results"))

    def images(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._record("images", keywords=keywords, **kwargs)
        return fake_results("images", kwargs.get("max_results"))

    def news(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._record("news", keywords=keywords, **kwargs)
        return fake_results("news", kwargs.get("max_results"))

    def videos(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._record("videos", keywords=keywords, **kwargs)
        return fake_results("videos", kwargs.get("max_results"))

    def books(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._record("books", keywords=keywords, **kwargs)
        return fake_results("books", kwargs.get("max_results"))


class TimeoutFakeDDGS(_BaseFakeDDGS):
    """
    Fake that simulates network timeouts for every category call.
    """

    def text(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise TimeoutException("Simulated timeout error")

    def images(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise TimeoutException("Simulated timeout error")

    def news(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise TimeoutException("Simulated timeout error")

    def videos(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise TimeoutException("Simulated timeout error")

    def books(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise TimeoutException("Simulated timeout error")


class ErrorFakeDDGS(_BaseFakeDDGS):
    """
    Fake that simulates generic engine errors for every category call.
    """

    def text(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise DDGSException("Simulated engine error")

    def images(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise DDGSException("Simulated engine error")

    def news(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise DDGSException("Simulated engine error")

    def videos(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise DDGSException("Simulated engine error")

    def books(self, keywords: str, **kwargs: Any) -> List[Dict[str, Any]]:
        raise DDGSException("Simulated engine error")


# -------------------------------
# In-memory transport harness
# -------------------------------

def in_memory_transport() -> Tuple[
    MemoryObjectReceiveStream[SessionMessage | Exception],  # server_read
    MemoryObjectSendStream[SessionMessage],                 # server_write
    MemoryObjectReceiveStream[SessionMessage | Exception],  # client_read
    MemoryObjectSendStream[SessionMessage],                 # client_write
]:
    """
    Create bidirectional anyio memory streams connecting a client and a server.

    Returns:
      (server_read, server_write, client_read, client_write)
    """
    c2s_send, c2s_recv = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    s2c_send, s2c_recv = anyio.create_memory_object_stream[SessionMessage | Exception](0)

    # Server reads what client writes, and writes what client reads.
    server_read = c2s_recv
    server_write = s2c_send

    # Client reads what server writes, and writes what server reads.
    client_read = s2c_recv
    client_write = c2s_send

    return server_read, server_write, client_read, client_write


# -------------------------------
# Server/Client runner fixture
# -------------------------------

@pytest.fixture
def run_server_client(monkeypatch: pytest.MonkeyPatch) -> Callable[[Type[_BaseFakeDDGS]], AsyncIterator[ClientSession]]:
    """
    Returns an async context manager callable you can use like:

        async with run_server_client(SuccessFakeDDGS) as client:
            await client.initialize()
            ...

    The expected server contract (defined by tests for TDD):
      - Module path: servers.ddgs_multisearch.server
      - Exports a function create_server() -> mcp.server.lowlevel.server.Server
      - The server module imports 'import ddgs' and uses ddgs.DDGS internally.
    """

    @asynccontextmanager
    async def _runner(ddgs_cls: Type[_BaseFakeDDGS]):
        # Import the target server module (expected to exist in later implementation)
        server_module = importlib.import_module("servers.ddgs_multisearch.server")

        # Ensure the server module uses our fake DDGS class (no real HTTP)
        # We expect the target module to `import ddgs` and then use ddgs.DDGS
        # So we monkeypatch the DDGS symbol on that imported ddgs module.
        monkeypatch.setattr(server_module.ddgs, "DDGS", ddgs_cls, raising=False)

        # Build server instance per contract
        create_server: Callable[[], Any] = getattr(server_module, "create_server")
        server = create_server()

        # Memory transport
        server_read, server_write, client_read, client_write = in_memory_transport()

        # Create initialization options from the server
        init_opts = server.create_initialization_options(NotificationOptions())

        async with anyio.create_task_group() as tg:
            # Run the server loop concurrently
            tg.start_soon(server.run, server_read, server_write, init_opts, False, False)

            # Create a client bound to the opposite ends and initialize handshake
            client = ClientSession(client_read, client_write)
            await client.initialize()

            try:
                yield client
            finally:
                # Stop the server loop
                tg.cancel_scope.cancel()

    return _runner