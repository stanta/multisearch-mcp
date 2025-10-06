# multisearch-mcp

Unified multi-category DuckDuckGo Search (DDGS) Model Context Protocol (MCP) server.

This server exposes five tools, one per DDGS category:
- text_search
- image_search
- news_search
- video_search
- book_search

All tools forward common DDGS options (backend, region, safesearch, page, max_results) and return a normalized object with "results": [].

## Features
- Five dedicated tools for search categories (text/images/news/videos/books)
- Pass-through of key DDGS parameters
- Simple structured output for easy client consumption
- Clear error mapping for timeouts and engine errors

## Requirements
- Python 3.13+
- Dependencies:
  - ddgs (DuckDuckGo Search)
  - mcp[cli]

## Installation
Using uv (recommended):
- uv sync
- uv sync --group dev  # to include developer/test dependencies

Using pip:
- python -m venv .venv && source .venv/bin/activate
- pip install -e .

## Using with an MCP host
This module exports an async entrypoint function `run(read_stream, write_stream)` that MCP hosts can load directly.
Module path: `servers.ddgs_multisearch.server`

Typical MCP hosts allow configuring a "python module" server by referencing the module path that exports `run`.

## Tool contract

- Names: "text_search", "image_search", "news_search", "video_search", "book_search"
- Shared input schema (properties):
  - query: string (required, non-empty)
  - backend: string (optional)
  - region: string (optional)
  - safesearch: string (optional)
  - page: integer (optional, default 1)
  - max_results: integer|null (optional)
- Output schema:
  - results: array of objects (category-specific shapes as provided by DDGS)

### Example call: tool "image_search" (images)
Input:
{
  "query": "python logo",
  "max_results": 2
}

Output:
{
  "results": [
    {
      "...": "category-specific fields, e.g., title, image, thumbnail, url"
    }
  ]
}

### Error handling
- Invalid input (e.g., empty query) → server returns a normalized MCP error
- DDGS timeouts → RuntimeError with "timeout: <message>"
- Other DDGS exceptions → RuntimeError with the original message
- Unknown exceptions bubble to the host framework

### Optional decorator wrappers (additive)
If the MCP decorator API is available, the module exposes thin decorator-based functions for each tool:
- [python.async def tool_text_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:226)
- [python.async def tool_image_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:231)
- [python.async def tool_news_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:237)
- [python.async def tool_video_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:243)
- [python.async def tool_book_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:249)

These wrappers are optional and only defined if the decorator import succeeds. The primary, low-level registration remains in [python.def create_server()](servers/ddgs_multisearch/server.py:255).

### Legacy compatibility shim (optional)
A back-compat multiplexed tool named "search" can be enabled via an environment flag:
- MULTISEARCH_ENABLE_LEGACY_SEARCH=1 (accepted truthy values: "1", "true", "yes", "on")

When enabled:
- [python.def create_server()](servers/ddgs_multisearch/server.py:255) registers a legacy tool named "search".
- Input schema matches the old multiplexed contract and includes a required "category" with enum ["text","images","news","videos","books"], in addition to the shared options.
- Output schema matches the standard { "results": array<object> }.

Behavior:
- Calls to "search" validate "query" and "category", then delegate to the corresponding per-category tool after removing the "category" key. By default the shim is disabled and "search" is not listed.

## Development
- Install dev deps: uv sync --group dev
- Run tests: uv run pytest -q

## License
See LICENSE for details.

## Add this MCP server to popular IDEs (VS Code, Cursor, Claude Desktop)

The server exposes an async entrypoint [run()](servers/ddgs_multisearch/server.py:342) and builder [create_server()](servers/ddgs_multisearch/server.py:255). Most MCP clients prefer launching a local process that speaks stdio. Create a tiny launcher script and then reference it in your IDE’s MCP configuration.

1) Create a stdio launcher script
- Save the following as [serve.py](serve.py) at the root of this repo.

```python
import anyio
from mcp.server.stdio import stdio_server
from servers.ddgs_multisearch.server import run as run_server

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await run_server(read_stream, write_stream)

if __name__ == "__main__":
    anyio.run(main)
```

Notes:
- Ensure the repo is on disk and Python can import it. If needed, set PYTHONPATH to your workspace root in the IDE config examples below.
- The launcher calls the same [run()](servers/ddgs_multisearch/server.py:342) you can embed directly in hosts that support Python-module loading.

### Optional decorator wrappers (additive)
If the MCP decorator API is available, the module exposes thin decorator-based functions for each tool:
- [python.async def tool_text_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:225)
- [python.async def tool_image_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:231)
- [python.async def tool_news_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:237)
- [python.async def tool_video_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:243)
- [python.async def tool_book_search(arguments: Dict[str, Any])](servers/ddgs_multisearch/server.py:249)

These wrappers are optional and only defined if the decorator import succeeds. The primary, low-level registration remains in [python.def create_server()](servers/ddgs_multisearch/server.py:255).

### Legacy compatibility shim (optional)
A back-compat multiplexed tool named "search" can be enabled via an environment flag:
- MULTISEARCH_ENABLE_LEGACY_SEARCH=1 (accepted truthy values: "1", "true", "yes", "on")

When enabled:
- [python.def create_server()](servers/ddgs_multisearch/server.py:255) registers a legacy tool named "search".
- Input schema matches the old multiplexed contract and includes a required "category" with enum ["text","images","news","videos","books"], in addition to the shared options.
- Output schema matches the standard { "results": array<object> }.

Behavior:
- Calls to "search" validate "query" and "category", then delegate to the corresponding per-category tool after removing the "category" key. By default the shim is disabled and "search" is not listed.

2) Visual Studio Code (GitHub Copilot MCP)
Option A — Workspace-scoped server via [.vscode/mcp.json](.vscode/mcp.json):
- Create .vscode/mcp.json in your workspace with:
```json
{
  "servers": {
    "multisearch-mcp": {
      "command": "python",
      "args": ["serve.py"],
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    }
  }
}
```
- Start a Copilot chat and run MCP tools after VS Code prompts you to trust the server.

Option B — Add globally via Command Palette:
- Run “MCP: Add Server”, choose Command type, then:
  - Command: python
  - Args: ["serve.py"]
  - Choose Global (user) or Workspace scope.

Option C — CLI:
```bash
code --add-mcp "{\"name\":\"multisearch-mcp\",\"command\":\"python\",\"args\":[\"serve.py\"]}"
```

Optional: Dev Containers
- In devcontainer.json under customizations.vscode.mcp.servers:
```json
{
  "customizations": {
    "vscode": {
      "mcp": {
        "servers": {
          "multisearch-mcp": {
            "command": "python",
            "args": ["serve.py"]
          }
        }
      }
    }
  }
}
```

3) Cursor IDE
Project-level config via [.cursor/mcp.json](.cursor/mcp.json):
```json
{
  "mcpServers": {
    "multisearch-mcp": {
      "command": "python",
      "args": ["serve.py"],
      "env": {
        "PYTHONPATH": "${workspaceRoot}"
      }
    }
  }
}
```
Global (UI): Cursor Settings → MCP → Add Server → Command = python, Args = ["serve.py"].

4) Claude Desktop
Option A — UI
- Open Claude Desktop → Settings → Developer → Model Context Protocol → Add Server:
  - Command: python
  - Args: ["serve.py"]
  - Optionally set an env variable PYTHONPATH pointing to your repo root if imports are not found.

Option B — Config file (typical structure)
- Edit your Claude Desktop MCP config (platform-specific path), add:
```json
{
  "mcpServers": {
    "multisearch-mcp": {
      "command": "python",
      "args": ["serve.py"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/your/checkout"
      }
    }
  }
}
```

Security and trust notes
- MCP servers can execute code. Only enable servers you trust.
- VS Code and other clients will prompt you to confirm trust on first run.
- Avoid hardcoding secrets in configs. Use environment variables or the IDE’s secret store where available.

Verification
- After adding the server, list tools in your client. You should see five tools: text_search, image_search, news_search, video_search, book_search.
- Try a call to the "image_search" tool with a simple query to confirm you receive a "results" array as described in the Tool contract section above.
