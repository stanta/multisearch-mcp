import anyio
from mcp.server.stdio import stdio_server
from servers.ddgs_multisearch.server import run as run_server


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await run_server(read_stream, write_stream)


if __name__ == "__main__":
    anyio.run(main)