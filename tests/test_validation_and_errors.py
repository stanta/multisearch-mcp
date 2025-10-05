import pytest

from tests.conftest import ErrorFakeDDGS, SuccessFakeDDGS, TimeoutFakeDDGS


def _extract_error_text(result) -> str:
    # Server-side errors are returned in CallToolResult.content as TextContent blocks
    texts = []
    for block in result.content:
        if getattr(block, "type", None) == "text":
            texts.append(block.text)
    return "\n".join(texts).lower()


@pytest.mark.anyio
async def test_input_validation_missing_query_is_error(run_server_client):
    async with run_server_client(SuccessFakeDDGS) as client:
        # Prime tool schema (ensures server has the tool schema cached)
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        # Missing "query"
        result = await client.call_tool(
            "search",
            {
                "category": "text",
                # "query": missing
            },
        )

        assert result.isError is True
        msg = _extract_error_text(result)
        # Accept a variety of reasonable validation messages
        assert "validation" in msg or "invalid" in msg or "missing" in msg


@pytest.mark.anyio
async def test_timeout_error_is_propagated(run_server_client):
    async with run_server_client(TimeoutFakeDDGS) as client:
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        result = await client.call_tool(
            "search",
            {
                "category": "images",
                "query": "python",
            },
        )

        assert result.isError is True
        msg = _extract_error_text(result)
        assert "timeout" in msg


@pytest.mark.anyio
async def test_generic_engine_error_is_propagated(run_server_client):
    async with run_server_client(ErrorFakeDDGS) as client:
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        result = await client.call_tool(
            "search",
            {
                "category": "text",
                "query": "python",
            },
        )

        assert result.isError is True
        msg = _extract_error_text(result)
        assert "simulated engine error" in msg