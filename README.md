# multisearch-mcp

Unified multi-category DuckDuckGo Search (DDGS) Model Context Protocol (MCP) server.

This server exposes a single tool, "search", that multiplexes DDGS categories:
- text
- images
- news
- videos
- books

The tool forwards common DDGS options (backend, region, safesearch, page, max_results) and returns a normalized object with "results": [].

## Features
- One tool for multiple search categories (text/images/news/videos/books)
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

- Name: "search"
- Input schema (properties):
  - query: string (required, non-empty)
  - category: string enum ["text","images","news","videos","books"] (required)
  - backend: string (optional)
  - region: string (optional)
  - safesearch: string (optional)
  - page: integer (optional, default 1)
  - max_results: integer|null (optional)
- Output schema:
  - results: array of objects (category-specific shapes as provided by DDGS)

### Example call (images)
Input:
{
  "category": "images",
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

## Development
- Install dev deps: uv sync --group dev
- Run tests: uv run pytest -q

## License
See LICENSE for details.

## Add this MCP server to popular IDEs (VS Code, Cursor, Claude Desktop)

The server exposes an async entrypoint [run()](servers/ddgs_multisearch/server.py:133) and builder [create_server()](servers/ddgs_multisearch/server.py:46). Most MCP clients prefer launching a local process that speaks stdio. Create a tiny launcher script and then reference it in your IDE’s MCP configuration.

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
- The launcher calls the same [run()](servers/ddgs_multisearch/server.py:133) you can embed directly in hosts that support Python-module loading.

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
- After adding the server, list tools in your client. You should see a single tool named "search" as declared in the tool listing handler of [create_server()](servers/ddgs_multisearch/server.py:55).
- Try a call with category "images" and a simple query to confirm you receive a "results" array as described in the Tool contract section above.
