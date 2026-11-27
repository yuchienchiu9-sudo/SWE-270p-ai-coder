"""Two scoped LLM specialists using live MCP results, not invented menu data."""
from llm import generate_json
from quickdelivery.mcp_client import call_tools


def recommend_food(preference: str, max_price: float, destination: str) -> dict:
    """Restaurant agent recommends IDs; delivery agent ranks them with MCP ETAs.

    Each specialist has its own LLM request and limited scope. The orchestrator
    deterministically fetches MCP data and validates model-generated IDs.
    No order is placed by AI.
    """
    dishes, t1 = __import__("asyncio").run(call_tools([("search_dishes", {"max_price": float(max_price), "spicy_only": "spicy" in preference.lower()})]))
    candidates = dishes[0]
    if not candidates:
        return {"recommendations": [], "trace": t1, "agent_notes": [], "usage": []}
    prompt = ("You are Restaurant Agent. Based ONLY on these dishes, select up to 3 item IDs matching the customer preference. "
              "Return JSON object {\"item_ids\": [\"...\"], \"reason\": \"...\"}. "
              f"Preference: {preference!r}. Dishes: {candidates!r}")
    chosen, u1 = generate_json(prompt)
    allowed = {x["id"]: x for x in candidates}
    ids = [i for i in chosen.get("item_ids", []) if isinstance(i, str) and i in allowed][:3]
    if not ids:
        ids = [x["id"] for x in candidates[:3]]
    restaurant_ids = list(dict.fromkeys(allowed[i]["restaurant_id"] for i in ids))
    routes, t2 = __import__("asyncio").run(call_tools([("estimate_delivery", {"restaurant_id": rid, "destination": destination}) for rid in restaurant_ids]))
    route_by_id = {x["restaurant_id"]: x for x in routes}
    selections = [{**allowed[i], "delivery": route_by_id[allowed[i]["restaurant_id"]]} for i in ids]
    delivery_prompt = ("You are Delivery Agent. Compare these REAL TOOL RESULTS (simulated ETAs, not actual maps). "
                       "Return JSON {\"ranked_item_ids\": [\"...\"], \"reason\": \"...\"}. "
                       "Prefer faster delivery while respecting the customer's preference. "
                       f"Candidates: {selections!r}")
    ranked, u2 = generate_json(delivery_prompt)
    ordering = [i for i in ranked.get("ranked_item_ids", []) if isinstance(i,str) and i in ids]
    ordering += [i for i in ids if i not in ordering]
    by_id = {s["id"]:s for s in selections}
    return {"recommendations": [by_id[i] for i in ordering], "trace": t1+t2,
            "agent_notes": [{"agent": "Restaurant Agent", "reason": chosen.get("reason", "")}, {"agent": "Delivery Agent", "reason": ranked.get("reason", "")}],
            "usage": [{"agent": "Restaurant Agent", **u1.to_dict()}, {"agent": "Delivery Agent", **u2.to_dict()}]}
