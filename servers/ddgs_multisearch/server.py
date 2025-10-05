from __future__ import annotations

from typing import Any, Dict, List, Optional

import ddgs  # tests will monkeypatch ddgs.DDGS in this module namespace
from mcp.server.lowlevel.server import Server
from mcp.shared.session import RequestResponder  # for type only; provided by framework
from mcp.types import Tool


TOOL_NAME = "multisearch-mcp"
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


def create_server(ddgs_factory: Optional[callable] = None) -> Server:
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
        responder: RequestResponder,
    ):
        if name != TOOL_NAME:
            raise ValueError(f"Unknown tool: {name}")
        async with responder:
            # Validate inputs
            query = arguments.get("query")
            category = arguments.get("category")

            if not isinstance(query, str) or len(query.strip()) == 0:
                # Raising ValueError ensures server-normalized error (isError=True)
                raise ValueError("query is required and must be a non-empty string")
            if category not in CATEGORIES:
                raise ValueError(f"category must be one of {CATEGORIES}")

            # Build engine and select category method
            ddgs_instance = factory()
            try:
                method = getattr(ddgs_instance, category)
            except AttributeError as e:
                raise ValueError(f"Unsupported category: {category}") from e

            # Forward optional arguments if present
            fwd: Dict[str, Any] = {}
            for key in ("backend", "region", "safesearch", "page", "max_results"):
                if key in arguments and arguments[key] is not None:
                    fwd[key] = arguments[key]

            # Call engine: DDGS interface expects 'keywords' for the query string
            try:
                results = method(keywords=query, **fwd)
            except Exception as e:  # Map known DDGS exceptions to clearer messages
                # Prefer explicit mapping if ddgs.exceptions are available
                try:
                    TimeoutExc = ddgs.exceptions.TimeoutException  # type: ignore[attr-defined]
                except Exception:
                    TimeoutExc = None  # type: ignore[assignment]
                try:
                    DDGSExc = ddgs.exceptions.DDGSException  # type: ignore[attr-defined]
                except Exception:
                    DDGSExc = None  # type: ignore[assignment]

                if TimeoutExc is not None and isinstance(e, TimeoutExc):
                    # Ensure message contains "timeout" per tests
                    raise RuntimeError(f"timeout: {e}") from e
                if DDGSExc is not None and isinstance(e, DDGSExc):
                    # Propagate original message content
                    raise RuntimeError(str(e)) from e
                # Let unknown exceptions bubble to framework
                raise

            if results is None:
                results = []
            if not isinstance(results, list):
                raise RuntimeError("DDGS returned a non-list result")

            # Structured content result
            return {"results": results}

    return server


async def run(read_stream, write_stream, *, ddgs_factory: Optional[callable] = None) -> None:
    """
    Run the DDGS multi-search server over provided anyio-compatible streams.
    """
    server = create_server(ddgs_factory=ddgs_factory)
    # Server.run will derive capabilities from registered handlers.
    init_opts = server.create_initialization_options()
    await server.run(read_stream, write_stream, init_opts, False, False)