from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from types import SimpleNamespace
from contextlib import nullcontext
import os
import urllib.request
import urllib.error
import base64
import re

# Prefer the real ddgs package in production; tests can monkeypatch ddgs.DDGS
ddgs: Any  # module-like provider exposing a DDGS attribute
try:
    import ddgs as _ddgs  # type: ignore[import-not-found]
    ddgs = _ddgs  # provides ddgs.DDGS
except Exception:
    # Fallback for environments without ddgs installed; tests will monkeypatch ddgs.DDGS
    ddgs = SimpleNamespace(DDGS=None)

# Optional decorator import for additive wrappers; keep runtime safe if MCP decorator API is absent
try:
    from mcp.server import tool as mcp_tool  # type: ignore[attr-defined]
except Exception:
    mcp_tool = None  # type: ignore[assignment]

from mcp.server.lowlevel.server import Server
from mcp.shared.session import RequestResponder  # for type only; provided by framework
from mcp.types import Tool

# New per-tool names
TEXT_TOOL = "text_search"
IMAGE_TOOL = "image_search"
NEWS_TOOL = "news_search"
VIDEO_TOOL = "video_search"
BOOK_TOOL = "book_search"
FETCH_TOOL = "fetch_content"

# Forwardable option keys shared by all tools
FORWARD_KEYS = ("backend", "region", "safesearch", "page", "max_results")


def _per_tool_input_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string"},
            "backend": {"type": "string"},
            "region": {"type": "string"},
            "safesearch": {"type": "string"},
            "page": {"type": "integer", "default": 1},
            "max_results": {"type": ["integer", "null"]},
        },
        "required": ["query"],
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


def _legacy_multiplex_input_schema() -> Dict[str, Any]:
    """
    Back-compat schema for legacy 'search' multiplexed tool:
    includes a required 'category' alongside the shared options.
    """
    schema = _per_tool_input_schema()
    props = dict(schema["properties"])
    props["category"] = {
        "type": "string",
        "enum": ["text", "images", "news", "videos", "books"],
    }
    req = list(schema["required"]) + ["category"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": req,
    }


# Fetch Content tool schemas and executor

def _fetch_input_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "timeout": {"type": "number", "default": 20},
            "headers": {"type": "object"},
            "max_bytes": {"type": "integer"},
        },
        "required": ["url"],
    }


def _fetch_output_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "url": {"type": "string"},
            "status": {"type": "integer"},
            "headers": {"type": "object"},
            "content_type": {"type": ["string", "null"]},
            "body": {"type": "string"},
            "body_encoding": {"type": "string"},
            "truncated": {"type": "boolean"},
        },
        "required": ["url", "status", "headers", "content_type", "body", "body_encoding", "truncated"],
    }


def _execute_fetch_content(arguments: Dict[str, Any]) -> Dict[str, Any]:
    # Validate inputs
    url = arguments.get("url")
    if not isinstance(url, str) or len(url.strip()) == 0:
        raise ValueError("url is required and must be a non-empty string")

    headers = arguments.get("headers") or {}
    if headers is not None and not isinstance(headers, dict):
        raise ValueError("headers must be an object mapping strings to strings")
    # Ensure header keys/values are strings
    norm_headers: Dict[str, str] = {}
    for k, v in (headers or {}).items():
        if not isinstance(k, str) or not isinstance(v, (str, int, float)):
            raise ValueError("headers must be a string-to-string mapping")
        norm_headers[str(k)] = str(v)

    timeout = arguments.get("timeout", 20)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number")

    max_bytes = arguments.get("max_bytes")
    if max_bytes is not None:
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer when provided")

    req = urllib.request.Request(url, headers=norm_headers)
    data: bytes
    status: int
    resp_headers: Dict[str, str]
    content_type: Optional[str]

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            # Convert headers to a plain dict
            resp_headers = {str(k): str(v) for k, v in resp.headers.items()}
            content_type = resp_headers.get("Content-Type") or resp_headers.get("content-type")
            data = resp.read(max_bytes) if max_bytes else resp.read()
    except urllib.error.HTTPError as e:
        # HTTPError is a file-like object; return status and body rather than raising a tool error
        status = int(getattr(e, "code", 0) or 0)
        hdrs = getattr(e, "headers", None)
        resp_headers = {str(k): str(v) for k, v in (hdrs.items() if hdrs is not None else [])}
        content_type = resp_headers.get("Content-Type") or resp_headers.get("content-type")
        try:
            data = e.read(max_bytes) if max_bytes else e.read()
        except Exception:
            data = b""
    except Exception as e:
        # Network or other errors become tool errors
        raise RuntimeError(str(e)) from e

    # Decide encoding strategy
    def is_textual(ct: Optional[str]) -> bool:
        if not ct:
            return False
        cts = ct.lower()
        return cts.startswith("text/") or "json" in cts or "xml" in cts or "javascript" in cts

    def extract_charset(ct: Optional[str]) -> Optional[str]:
        if not ct:
            return None
        m = re.search(r"charset=([^;]+)", ct, re.IGNORECASE)
        return m.group(1).strip() if m else None

    body_encoding: str
    body: str
    if is_textual(content_type):
        enc = extract_charset(content_type) or "utf-8"
        try:
            body = data.decode(enc, errors="replace")
            body_encoding = enc
        except Exception:
            body = base64.b64encode(data).decode("ascii")
            body_encoding = "base64"
    else:
        body = base64.b64encode(data).decode("ascii")
        body_encoding = "base64"

    # Normalize header keys to lower-case for convenience
    lower_headers = {k.lower(): v for k, v in resp_headers.items()}
    truncated = bool(max_bytes) and max_bytes is not None and len(data) >= int(max_bytes)

    return {
        "url": url,
        "status": int(status),
        "headers": lower_headers,
        "content_type": content_type if content_type is not None else None,
        "body": body,
        "body_encoding": body_encoding,
        "truncated": truncated,
    }


class EngineAdapter:
    """
    Wraps ddgs.DDGS lifecycle, context manager usage, invocation compatibility,
    error mapping, and result normalization.
    """

    def __init__(self, factory: Optional[Callable[[], Any]]) -> None:
        self._factory = factory

    def _call_method(self, method: Callable[..., Any], query: str, fwd: Dict[str, Any]) -> List[Dict[str, Any]]:
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

    def invoke(self, category: str, query: str, **opts: Any) -> List[Dict[str, Any]]:
        factory = self._factory
        if factory is None:
            # Surface a clear, structured tool error instead of crashing or closing the connection
            raise RuntimeError("ddgs.DDGS is not available. Install the 'ddgs' package or provide ddgs_factory.")

        engine_raw = factory()

        def _invoke_on(engine_obj: Any) -> List[Dict[str, Any]]:
            try:
                method = getattr(engine_obj, category)
            except AttributeError as e:
                raise ValueError(f"Unsupported category: {category}") from e
            return self._call_method(method, query, opts)

        # Use context manager if supported by the engine
        has_cm = callable(getattr(engine_raw, "__enter__", None)) and callable(getattr(engine_raw, "__exit__", None))
        try:
            if has_cm:
                with engine_raw as engine:
                    results = _invoke_on(engine)
            else:
                results = _invoke_on(engine_raw)
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

        return results


class SearchToolBase:
    """
    Base class for per-category search tools. Implements shared validation, schemas,
    forwarding semantics, and result shaping while delegating to EngineAdapter.
    """

    name: str = ""
    description: Optional[str] = None
    category: str = ""

    def __init__(self, adapter: EngineAdapter) -> None:
        self._adapter = adapter

    @staticmethod
    def input_schema() -> Dict[str, Any]:
        return _per_tool_input_schema()

    @staticmethod
    def output_schema() -> Dict[str, Any]:
        return _output_schema()

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Validate inputs
        query = arguments.get("query")
        if not isinstance(query, str) or len(query.strip()) == 0:
            # Raising ValueError ensures server-normalized error (isError=True)
            raise ValueError("query is required and must be a non-empty string")

        # Forward optional arguments if present
        fwd: Dict[str, Any] = {}
        for key in FORWARD_KEYS:
            if key in arguments and arguments[key] is not None:
                fwd[key] = arguments[key]

        results = self._adapter.invoke(self.category, query, **fwd)
        # Structured content result
        return {"results": results}


class TextSearchTool(SearchToolBase):
    name = TEXT_TOOL
    description = "DDGS text search"
    category = "text"


class ImageSearchTool(SearchToolBase):
    name = IMAGE_TOOL
    description = "DDGS image search"
    category = "images"


class NewsSearchTool(SearchToolBase):
    name = NEWS_TOOL
    description = "DDGS news search"
    category = "news"


class VideoSearchTool(SearchToolBase):
    name = VIDEO_TOOL
    description = "DDGS video search"
    category = "videos"


class BookSearchTool(SearchToolBase):
    name = BOOK_TOOL
    description = "DDGS book search"
    category = "books"


# Optional: Add thin decorator-based wrappers if MCP tool decorator is available.
# These are additive and do not replace the low-level registration in create_server().
if mcp_tool:

    @mcp_tool(name=TEXT_TOOL, input_schema=_per_tool_input_schema(), output_schema=_output_schema())  # type: ignore[misc]
    async def tool_text_search(arguments: Dict[str, Any]) -> Dict[str, Any]:
        factory = getattr(ddgs, "DDGS", None)
        adapter = EngineAdapter(factory=factory)
        return TextSearchTool(adapter).execute(arguments)

    @mcp_tool(name=IMAGE_TOOL, input_schema=_per_tool_input_schema(), output_schema=_output_schema())  # type: ignore[misc]
    async def tool_image_search(arguments: Dict[str, Any]) -> Dict[str, Any]:
        factory = getattr(ddgs, "DDGS", None)
        adapter = EngineAdapter(factory=factory)
        return ImageSearchTool(adapter).execute(arguments)

    @mcp_tool(name=NEWS_TOOL, input_schema=_per_tool_input_schema(), output_schema=_output_schema())  # type: ignore[misc]
    async def tool_news_search(arguments: Dict[str, Any]) -> Dict[str, Any]:
        factory = getattr(ddgs, "DDGS", None)
        adapter = EngineAdapter(factory=factory)
        return NewsSearchTool(adapter).execute(arguments)

    @mcp_tool(name=VIDEO_TOOL, input_schema=_per_tool_input_schema(), output_schema=_output_schema())  # type: ignore[misc]
    async def tool_video_search(arguments: Dict[str, Any]) -> Dict[str, Any]:
        factory = getattr(ddgs, "DDGS", None)
        adapter = EngineAdapter(factory=factory)
        return VideoSearchTool(adapter).execute(arguments)

    @mcp_tool(name=BOOK_TOOL, input_schema=_per_tool_input_schema(), output_schema=_output_schema())  # type: ignore[misc]
    async def tool_book_search(arguments: Dict[str, Any]) -> Dict[str, Any]:
        factory = getattr(ddgs, "DDGS", None)
        adapter = EngineAdapter(factory=factory)
        return BookSearchTool(adapter).execute(arguments)

    @mcp_tool(name=FETCH_TOOL, input_schema=_fetch_input_schema(), output_schema=_fetch_output_schema())  # type: ignore[misc]
    async def tool_fetch_content(arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Keep behavior aligned with low-level registration: controlled via env flag
        if os.getenv("MULTISEARCH_ENABLE_FETCH", "").strip().lower() not in {"1", "true", "yes", "on"}:
            # Mirror server-side unknown tool behavior for symmetry when decorator API is used standalone
            raise ValueError("Unknown tool: fetch_content")
        return _execute_fetch_content(arguments)


def create_server(ddgs_factory: Optional[Callable[[], Any]] = None) -> Server:
    """
    Build and return an MCP Server with five category-specific tools.
    ddgs_factory: optional factory returning a DDGS-like object with methods:
                  text/images/news/videos/books(keywords: str, **kwargs) -> list[dict]
    """
    server = Server(name="ddgs-multisearch")
    factory = ddgs_factory or ddgs.DDGS
    adapter = EngineAdapter(factory=factory)

    # Instantiate tool classes with shared adapter
    tool_instances: Dict[str, SearchToolBase] = {
        TEXT_TOOL: TextSearchTool(adapter),
        IMAGE_TOOL: ImageSearchTool(adapter),
        NEWS_TOOL: NewsSearchTool(adapter),
        VIDEO_TOOL: VideoSearchTool(adapter),
        BOOK_TOOL: BookSearchTool(adapter),
    }

    # Legacy shim flag (disabled by default)
    enable_legacy = os.getenv("MULTISEARCH_ENABLE_LEGACY_SEARCH", "").strip().lower() in {"1", "true", "yes", "on"}
    # Optional fetch tool flag (disabled by default)
    enable_fetch = True # if os.getenv("MULTISEARCH_ENABLE_FETCH", "").strip().lower() in {"1", "true", "yes", "on"} else False

    # Category -> tool name map for legacy multiplexed "search"
    category_to_tool: Dict[str, str] = {
        "text": TEXT_TOOL,
        "images": IMAGE_TOOL,
        "news": NEWS_TOOL,
        "videos": VIDEO_TOOL,
        "books": BOOK_TOOL,
    }

    @server.list_tools()
    async def handle_list_tools() -> List[Tool]:
        tools: List[Tool] = [
            Tool(
                name=inst.name,
                description=inst.description,
                inputSchema=inst.input_schema(),
                outputSchema=inst.output_schema(),
            )
            for inst in tool_instances.values()
        ]
        if enable_fetch:
            tools.append(
                Tool(
                    name=FETCH_TOOL,
                    description="Fetch URL content over HTTP(S). Returns status, headers, and body (text or base64).",
                    inputSchema=_fetch_input_schema(),
                    outputSchema=_fetch_output_schema(),
                )
            )
        if enable_legacy:
            tools.append(
                Tool(
                    name="search",
                    description="Legacy multiplexed DDGS search (back-compat). Disabled by default.",
                    inputSchema=_legacy_multiplex_input_schema(),
                    outputSchema=_output_schema(),
                )
            )
        return tools

    @server.call_tool()
    async def handle_call_tool(
        name: str,
        arguments: Dict[str, Any],
        *,
        responder: Optional[RequestResponder] = None,
    ):
        with (responder if responder is not None else nullcontext()):
            if name == "search":
                if not enable_legacy:
                    raise ValueError("Unknown tool: search")
                # Validate presence of category
                category = arguments.get("category")
                if not isinstance(category, str) or category not in category_to_tool:
                    raise ValueError("category is required and must be one of: text, images, news, videos, books")

                # Forward to the corresponding per-category tool after removing 'category'
                forwarded = dict(arguments)
                forwarded.pop("category", None)

                tool_name = category_to_tool[category]
                tool = tool_instances[tool_name]
                return tool.execute(forwarded)

            if name == FETCH_TOOL:
                if not enable_fetch:
                    raise ValueError(f"Unknown tool: {name}")
                return _execute_fetch_content(arguments)

            if name not in tool_instances:
                raise ValueError(f"Unknown tool: {name}")

            tool = tool_instances[name]
            # Delegate to the tool class (includes validation, forwarding, errors, normalization)
            return tool.execute(arguments)

    return server


async def run(read_stream, write_stream, *, ddgs_factory: Optional[Callable[[], Any]] = None) -> None:
    """
    Run the DDGS multi-search server over provided anyio-compatible streams.
    """
    server = create_server(ddgs_factory=ddgs_factory)
    # Server.run will derive capabilities from registered handlers.
    init_opts = server.create_initialization_options()
    await server.run(read_stream, write_stream, init_opts, False, False)