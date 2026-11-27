"""Real stdio MCP transport smoke test, requires project's mcp dependency."""
import asyncio
import pytest

pytest.importorskip("mcp")


def test_domain_tools_over_real_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("QUICKDELIVERY_DB", str(tmp_path / "qd.db"))
    from quickdelivery.mcp_client import call_tools

    results, trace = asyncio.run(call_tools([
        ("list_restaurants", {}),
        ("get_menu", {"restaurant_id": "r1"}),
        ("estimate_delivery", {"restaurant_id": "r1", "destination": "UCI Campus"}),
        ("add_to_cart", {"session_id": "tester", "restaurant_id": "r1", "item_id": "m1", "quantity": 1}),
        ("get_cart", {"session_id": "tester"}),
    ]))
    assert len(results[0]) >= 4
    assert results[1]["items"][0]["name"]
    assert results[2]["simulated"] is True
    assert results[4]["total"] == 14.5
    assert len(trace) == 5 and all(not x["is_error"] for x in trace)
