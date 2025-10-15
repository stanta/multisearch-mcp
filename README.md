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

## Docker

This project ships with a production-ready multi-stage [Dockerfile](Dockerfile) and a convenience [docker-compose.yml](docker-compose.yml) to package and run the MCP server in a portable container.

Why containers for MCP?
- Reproducible: consistent Python and dependency versions
- Secure-by-default: non-root user, no host Python needed
- Stdio-friendly: the image starts [python.main()](serve.py:6) which speaks MCP over stdin/stdout

Build (local image):
```bash
docker build -t multisearch-mcp:local .
```

Run with stdio (attach stdin; MCP hosts can launch this command):
```bash
# The server communicates over stdin/stdout; keep -i to attach stdio.
docker run --rm -i multisearch-mcp:local
```

Using Docker Compose (recommended for local dev):
```bash
# Build the image
docker compose build

# Run with stdio attached (same behavior as plain docker run -i)
docker compose run --rm -i multisearch-mcp
```

### Ephemeral container lifecycle (auto-stop and auto-remove)

- This image is intended to run ephemerally under an MCP host.
- The MCP server exits automatically when STDIN closes (for example, when your IDE disconnects).
- Always include --rm so Docker deletes the container when it stops.

Examples:
```bash
# One-shot container that is removed on exit
docker run --rm -i multisearch-mcp:local

# Compose variant that removes the container when the run finishes
docker compose run --rm -i multisearch-mcp
```

Note:
- The image sets a stop signal in [Dockerfile](Dockerfile) so it shuts down quickly on docker stop.
- If the container exits immediately, ensure your host keeps STDIN open (-i).

Environment flags:
- MULTISEARCH_ENABLE_LEGACY_SEARCH: enable legacy multiplexed "search" tool (default: disabled)
- MULTISEARCH_ENABLE_FETCH: enable the "fetch_content" tool (docker-compose sets this to 1 by default)

Examples:
```bash
docker run --rm -i \
  -e MULTISEARCH_ENABLE_LEGACY_SEARCH=1 \
  -e MULTISEARCH_ENABLE_FETCH=1 \
  multisearch-mcp:local
```

Healthcheck:
- The image defines a HEALTHCHECK that validates importability of [python.def create_server()](servers/ddgs_multisearch/server.py:395). This ensures dependencies are installed and the module is wired before marking the container healthy.

Image details:
- Multi-stage build with uv to resolve and lock Python deps from [pyproject.toml](pyproject.toml)
- Non-root runtime user (mcpuser)
- Entrypoint/command: `python serve.py` which launches the stdio server via [python.main()](serve.py:6)

Notes for IDE MCP hosts:
- Most IDEs spawn a local process; you can point them at `python serve.py` directly as documented above. If you prefer containerized execution, configure your host to run `docker run --rm -i multisearch-mcp:local` as the command and keep stdin attached.

Troubleshooting:
- If the container exits immediately, ensure your MCP host kept stdin open (use `-i`).
- If you don’t see expected tools, verify env flags and list tools via your MCP client.
### Configure IDE clients to use the Dockerized MCP server

This server communicates over stdin/stdout. When running in a container you must keep STDIN attached. All examples below use the required interactive flag (-i). If your IDE allows specifying a command plus arguments for an MCP server, point it to Docker instead of a local Python process.

Key command used by IDEs (build the image first as shown above):
```bash
docker run --rm -i multisearch-mcp:local
```

You can also use Compose:
```bash
docker compose run --rm -i multisearch-mcp
```

Notes:
- Keep the -i flag so the client can speak MCP over stdio.
- Pass any feature flags via -e (see “Environment flags” above).
- If your IDE launches from a different working directory, prefer the plain docker run example over compose, or provide a fully-qualified -f path to your docker-compose.yml.

#### Visual Studio Code (GitHub Copilot MCP) — run via Docker

Option A — Workspace-scoped server via [.vscode/mcp.json](.vscode/mcp.json):
```json
{
  "servers": {
    "multisearch-mcp": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
        // Optional: pass feature flags
        // NOTE: env is usually preferred (see below), but some hosts only support args.
        // For portability, prefer the "env" block when supported by your client.
        "multisearch-mcp:local"
      ],
      "env": {
        // Optional: expose env flags to the container via Docker's -e if your host supports it.
        // When using this env block, most hosts DO NOT automatically translate to Docker -e.
        // In that case, add explicit "-e KEY=value" entries inside args instead.
        "PYTHONPATH": "${workspaceFolder}"
      }
    }
  }
}
```

Option B — Global (Command Palette):
- Run “MCP: Add Server”, choose Command type
  - Command: docker
  - Args: ["run","--rm","-i","multisearch-mcp:local"]

Option C — CLI:
```bash
code --add-mcp "{\"name\":\"multisearch-mcp\",\"command\":\"docker\",\"args\":[\"run\",\"--rm\",\"-i\",\"multisearch-mcp:local\"]}"
```

To enable optional tools, add -e flags inside args, for example:
```json
"args": ["run","--rm","-i",
  "-e","MULTISEARCH_ENABLE_LEGACY_SEARCH=1",
  "-e","MULTISEARCH_ENABLE_FETCH=1",
  "multisearch-mcp:local"
]
```

#### Cursor — project-level [.cursor/mcp.json](.cursor/mcp.json)
```json
{
  "mcpServers": {
    "multisearch-mcp": {
      "command": "docker",
      "args": ["run","--rm","-i",
        "-e","MULTISEARCH_ENABLE_FETCH=1",
        "multisearch-mcp:local"
      ]
    }
  }
}
```

If you prefer Compose and your IDE’s working directory is the repo root:
```json
{
  "mcpServers": {
    "multisearch-mcp": {
      "command": "docker",
      "args": ["compose","run","--rm","-i","multisearch-mcp"]
    }
  }
}
```
If the working directory is not the repo root, use a fully-qualified Compose file:
```json
{
  "mcpServers": {
    "multisearch-mcp": {
      "command": "docker",
      "args": ["compose","-f","/absolute/path/to/docker-compose.yml","run","--rm","-i","multisearch-mcp"]
    }
  }
}
```

#### Claude Desktop — config file example
Edit your Claude Desktop MCP config (platform-specific path) to use Docker as the launcher:
```json
{
  "mcpServers": {
    "multisearch-mcp": {
      "command": "docker",
      "args": ["run","--rm","-i",
        "-e","MULTISEARCH_ENABLE_FETCH=1",
        "multisearch-mcp:local"
      ]
    }
  }
}
```

#### Mapping environment variables and network access

- Feature flags:
  - MULTISEARCH_ENABLE_LEGACY_SEARCH (truthy enables legacy multiplexed "search")
  - MULTISEARCH_ENABLE_FETCH (truthy enables the fetch_content tool)
- Pass them via Docker:
  - Add "-e","KEY=value" pairs in the args list for your MCP host’s Docker command.
- Networking:
  - This server makes outbound HTTPS requests when fetch_content is enabled. Typical Docker defaults work without extra flags. If you use a corporate proxy, inject standard proxy env variables (HTTP_PROXY/HTTPS_PROXY/NO_PROXY) with additional -e entries.

#### Verification (Docker)

- List tools in your MCP client after adding the server. You should see:
  - text_search, image_search, news_search, video_search, book_search
  - fetch_content (only if MULTISEARCH_ENABLE_FETCH is truthy)
- Test a tool call (e.g., "image_search") and confirm the structured {"results": [...]} response.
- If the container exits immediately, ensure your host kept stdin open (-i) and that your configuration uses "docker run --rm -i ...".

### Optional: Use Docker Desktop’s MCP Toolkit (Gateway)

Docker Desktop provides an MCP “gateway” that can host and manage containerized MCP servers and present them to MCP clients via a single endpoint.

High-level flow:
1) Start the gateway (via Docker Desktop UI or CLI).
2) Register this server’s image/tag (multisearch-mcp:local) with the gateway.
3) In your IDE’s MCP configuration, point to the gateway’s connection instead of launching Docker directly.

This approach centralizes multiple MCP servers behind one connection and can simplify team setups. For details, consult Docker’s MCP Toolkit documentation. The server itself remains unchanged; it still runs [python.main()](serve.py:6) inside the container and speaks MCP over stdio.
