import pytest

from tests.conftest import SuccessFakeDDGS


@pytest.mark.anyio
async def test_argument_forwarding_text_category(run_server_client):
    async with run_server_client(SuccessFakeDDGS) as client:
        # Ensure tool exists
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        # Arguments to forward
        args = {
            "category": "text",
            "query": "python",
            "backend": "html",
            "region": "us-en",
            "safesearch": "moderate",
            "page": 2,
            "max_results": 4,
        }

        result = await client.call_tool("search", args)
        assert result.isError is False

        # Verify the server selected text() and forwarded args
        inst = SuccessFakeDDGS.last_instance
        assert inst is not None, "DDGS should be constructed by the server"
        assert "text" in inst.last_calls, "Server should call the text() method for category=text"

        forwarded = inst.last_calls["text"]
        # The server should pass the query as 'keywords' per DDGS interface
        assert forwarded.get("keywords") == args["query"]
        # Optional parameters forwarded intact
        assert forwarded.get("backend") == args["backend"]
        assert forwarded.get("region") == args["region"]
        assert forwarded.get("safesearch") == args["safesearch"]
        assert forwarded.get("page") == args["page"]
        assert forwarded.get("max_results") == args["max_results"]


@pytest.mark.anyio
async def test_argument_forwarding_images_category(run_server_client):
    async with run_server_client(SuccessFakeDDGS) as client:
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        args = {
            "category": "images",
            "query": "python logo",
            "backend": "lite",
            "region": "uk-en",
            "safesearch": "off",
            "page": 3,
            "max_results": 2,
        }

        result = await client.call_tool("search", args)
        assert result.isError is False

        inst = SuccessFakeDDGS.last_instance
        assert inst is not None, "DDGS should be constructed by the server"
        assert "images" in inst.last_calls, "Server should call the images() method for category=images"

        forwarded = inst.last_calls["images"]
        assert forwarded.get("keywords") == args["query"]
        assert forwarded.get("backend") == args["backend"]
        assert forwarded.get("region") == args["region"]
        assert forwarded.get("safesearch") == args["safesearch"]
        assert forwarded.get("page") == args["page"]
        assert forwarded.get("max_results") == args["max_results"]


@pytest.mark.anyio
async def test_empty_query_rejected_before_engine_call(run_server_client):
    async with run_server_client(SuccessFakeDDGS) as client:
        tools = (await client.list_tools()).tools
        assert any(t.name == "search" for t in tools)

        # Empty query should be rejected by server-side validation
        result = await client.call_tool(
            "search",
            {
                "category": "text",
                "query": "",
            },
        )

        assert result.isError is True

        # Ensure DDGS was not called at all
        inst = SuccessFakeDDGS.last_instance
        # It is acceptable that the server may not even construct DDGS if it validates first
        if inst is not None:
            assert inst.call_count == 0, "Engine should not be called when input is invalid"