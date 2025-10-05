from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from types import SimpleNamespace
from contextlib import nullcontext

# Prefer the real ddgs package in production; tests can monkeypatch ddgs.DDGS
try:
    import ddgs as _ddgs  # type: ignore[import-not-found]
    ddgs = _ddgs  # provides ddgs.DDGS
except Exception:
    # Fallback for environments without ddgs installed; tests will monkeypatch ddgs.DDGS
    ddgs = SimpleNamespace(DDGS=None)
from mcp.server.lowlevel.server import Server
from mcp.shared.session import RequestResponder  # for type only; provided by framework
from mcp.types import Tool


TOOL_NAME = "search"
CATEGORIES = ["text", "images", "news", "videos", "books"]


def _input_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string"},
            "category": {"type": "string", "enum": CATEGORIES},
            "backend": {"type": "string"},
            "region": {"type": "string"},
            "safesearch": {"type": "string"},
            "page": {"type": "integer", "default": 1},
            "max_results": {"type": ["integer", "null"]},
        },
        "required": ["query", "category"],
    }


def _output_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "results": {
                "type": "array",
                "items": {"type": "object"},
            }
        },
        "required": ["results"],
    }


def create_server(ddgs_factory: Optional[Callable[[], Any]] = None) -> Server:
    """
    Build and return an MCP Server with a single multiplexed 'search' tool.
    ddgs_factory: optional factory returning a DDGS-like object with methods:
                  text/images/news/videos/books(keywords: str, **kwargs) -> list[dict]
    """
    server = Server(name="ddgs-multisearch")
    factory = ddgs_factory or ddgs.DDGS

    @server.list_tools()
    async def handle_list_tools() -> List[Tool]:
        return [
            Tool(
                name=TOOL_NAME,
                description="Unified multi-category search via DDGS across text/images/news/videos/books.",
                inputSchema=_input_schema(),
                outputSchema=_output_schema(),
            )
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str,
        arguments: Dict[str, Any],
        *,
        responder: Optional[RequestResponder] = None,
    ):
        if name != TOOL_NAME:
            raise ValueError(f"Unknown tool: {name}")
        with (responder if responder is not None else nullcontext()):
            # Validate inputs
            query = arguments.get("query")
            category = arguments.get("category")

            if not isinstance(query, str) or len(query.strip()) == 0:
                # Raising ValueError ensures server-normalized error (isError=True)
                raise ValueError("query is required and must be a non-empty string")
            if category not in CATEGORIES:
                raise ValueError(f"category must be one of {CATEGORIES}")

            # Build engine and select category method
            if factory is None:
                # Surface a clear, structured tool error instead of crashing or closing the connection
                raise RuntimeError("ddgs.DDGS is not available. Install the 'ddgs' package or provide ddgs_factory.")
            engine_raw = factory()

            # Forward optional arguments if present
            fwd: Dict[str, Any] = {}
            for key in ("backend", "region", "safesearch", "page", "max_results"):
                if key in arguments and arguments[key] is not None:
                    fwd[key] = arguments[key]

            def _invoke(engine_obj: Any) -> List[Dict[str, Any]]:
                try:
                    method = getattr(engine_obj, category)
                except AttributeError as e:
                    raise ValueError(f"Unsupported category: {category}") from e

                # Try multiple calling conventions to support different ddgs versions:
                # 1) keywords=... (older ddgs)
                # 2) query=... (newer ddgs)
                # 3) positional (broad compatibility and unbound/class-level edge cases)
                try:
                    return method(keywords=query, **fwd)
                except TypeError:
                    try:
                        return method(query=query, **fwd)
                    except TypeError:
                        return method(query, **fwd)

            # Use context manager if supported by the engine
            has_cm = callable(getattr(engine_raw, "__enter__", None)) and callable(getattr(engine_raw, "__exit__", None))
            try:
                if has_cm:
                    with engine_raw as engine:
                        results = _invoke(engine)
                else:
                    results = _invoke(engine_raw)
            except Exception as e:
                # Map errors by message content to avoid depending on ddgs.exceptions at import time
                msg = str(e)
                name = type(e).__name__.lower()
                if "timeout" in msg.lower() or "timeout" in name:
                    # Ensure the substring "timeout" is present as tests expect
                    raise RuntimeError(f"timeout: {e}") from e
                # Propagate other engine errors preserving message
                raise RuntimeError(msg) from e

            if results is None:
                results = []
            if not isinstance(results, list):
                raise RuntimeError("DDGS returned a non-list result")

            # Structured content result
            return {"results": results}

    return server


async def run(read_stream, write_stream, *, ddgs_factory: Optional[Callable[[], Any]] = None) -> None:
    """
    Run the DDGS multi-search server over provided anyio-compatible streams.
    """
    server = create_server(ddgs_factory=ddgs_factory)
    # Server.run will derive capabilities from registered handlers.
    init_opts = server.create_initialization_options()
    await server.run(read_stream, write_stream, init_opts, False, False)