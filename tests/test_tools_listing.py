import pytest

from tests.conftest import CATEGORIES, SuccessFakeDDGS


def _is_integer_or_null(schema: dict) -> bool:
    """
    Accept JSON Schemas that allow integer or null via:
      - {"type": ["integer", "null"]}
      - {"anyOf": [{"type":"integer"}, {"type":"null"}]}
    """
    t = schema.get("type")
    if isinstance(t, list):
        return "integer" in t and "null" in t
    if t == "integer":
        # Also acceptable if not explicitly allowing null
        return True
    anyof = schema.get("anyOf")
    if isinstance(anyof, list):
        types = {item.get("type") for item in anyof if isinstance(item, dict)}
        return "integer" in types and "null" in types
    return False


@pytest.mark.anyio
async def test_list_tools_exposes_search_tool(run_server_client):
    # Will fail until the server is implemented at servers/ddgs_multisearch/server.py
    async with run_server_client(SuccessFakeDDGS) as client:
        result = await client.list_tools()
        tools = result.tools

        # Exactly one multi-search tool
        assert isinstance(tools, list)
        assert len(tools) == 1

        tool = tools[0]
        assert tool.name == "search"
        assert tool.description is None or isinstance(tool.description, str)

        # Validate input schema shape
        schema = tool.inputSchema
        assert isinstance(schema, dict)
        props = schema.get("properties", {})
        required = schema.get("required", [])

        # Required fields
        assert "query" in required
        assert "category" in required

        # query: string
        assert "query" in props and props["query"].get("type") == "string"

        # category: enum of expected categories
        assert "category" in props
        cat_enum = props["category"].get("enum")
        assert isinstance(cat_enum, list)
        assert set(cat_enum) == set(CATEGORIES)

        # Optional fields presence and basic typing
        assert "backend" in props and props["backend"].get("type") == "string"
        assert "region" in props and props["region"].get("type") == "string"
        assert "safesearch" in props and props["safesearch"].get("type") == "string"

        # page: integer with default 1
        assert "page" in props
        page_type = props["page"].get("type")
        assert page_type in ("integer", "number")
        assert props["page"].get("default", 1) == 1

        # max_results: integer or null (optional)
        assert "max_results" in props
        assert _is_integer_or_null(props["max_results"])

        # Output schema is optional; if provided, it should accept an object
        # with a "results" array of objects (or be omitted).
        if tool.outputSchema is not None:
            oschema = tool.outputSchema
            assert oschema.get("type") == "object"
            props = oschema.get("properties", {})
            assert "results" in props
            results_schema = props["results"]
            assert results_schema.get("type") == "array"
            items = results_schema.get("items")
            assert isinstance(items, dict)
            assert items.get("type") == "object"