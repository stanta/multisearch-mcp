import pytest

from tests.conftest import SuccessFakeDDGS


@pytest.mark.anyio
async def test_search_text_success(run_server_client):
    async with run_server_client(SuccessFakeDDGS) as client:
        # Ensure tool is listed (also primes client-side schema cache)
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        # Call the multi-search tool for text
        max_results = 3
        result = await client.call_tool(
            "search",
            {
                "category": "text",
                "query": "python",
                "max_results": max_results,
            },
        )

        # Should not be an error
        assert result.isError is False

        # Contract: structuredContent returns normalized objects under "results"
        assert isinstance(result.structuredContent, dict)
        assert "results" in result.structuredContent
        data = result.structuredContent["results"]
        assert isinstance(data, list)
        assert len(data) == max_results

        # Verify expected text fields
        for item in data:
            assert set(item.keys()) >= {"title", "href", "body"}


@pytest.mark.anyio
async def test_search_images_success(run_server_client):
    async with run_server_client(SuccessFakeDDGS) as client:
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        result = await client.call_tool(
            "search",
            {
                "category": "images",
                "query": "python logo",
                "max_results": 2,
            },
        )

        assert result.isError is False
        assert isinstance(result.structuredContent, dict)
        assert "results" in result.structuredContent
        data = result.structuredContent["results"]
        assert isinstance(data, list)
        assert len(data) == 2

        # Verify expected image fields
        for item in data:
            assert set(item.keys()) >= {"title", "image", "thumbnail", "url"}