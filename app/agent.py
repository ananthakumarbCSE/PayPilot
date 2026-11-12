"""Tool-calling commerce agent with grounded multi-source product discovery."""
import json
import os
import requests

from .catalog import search_catalog, get_product

TOOLS = [
    {"type": "function", "function": {
        "name": "search_catalog",
        "description": (
            "Search PayPilot's connected product sources for relevant items. Search using the actual "
            "product category/model and customer constraints. Return only matching products; never substitute "
            "an unrelated item. Results identify whether they are PayPilot demo products, DummyJSON sample "
            "products, or eBay marketplace listings."
        ),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Product keywords, category, brand/model and useful constraints"}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "prepare_cart",
        "description": (
            "Prepare a PayPilot Sandbox proposal using only checkout_eligible product IDs returned by "
            "search_catalog. Do not use eBay listing IDs: those are external view-only listings and must be "
            "opened on eBay. This does not charge the customer."
        ),
        "parameters": {"type": "object", "properties": {
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "product_id": {"type": "string"}, "quantity": {"type": "integer", "minimum": 1, "maximum": 5}
            }, "required": ["product_id", "quantity"]}}
        }, "required": ["items"]}
    }}
]


def _prepare_cart(args):
    result, total_cents = [], 0
    errors = []
    for requested in args.get("items", []):
        product = get_product(str(requested.get("product_id", "")))
        qty = max(1, min(5, int(requested.get("quantity", 1))))
        if not product:
            errors.append("One selected product is not eligible for PayPilot checkout.")
            continue
        cents = round(float(product["price"]) * 100) * qty
        total_cents += cents
        result.append({
            "id": product["id"], "name": product["name"], "quantity": qty,
            "unit_price": f"{float(product['price']):.2f}", "line_total": f"{cents/100:.2f}",
            "description": product.get("description", ""),
        })
    if not result:
        return {"error": "; ".join(errors) or "No valid checkout products were selected.", "items": [],
                "total": "0.00", "currency": "USD"}
    return {"items": result, "total": f"{total_cents/100:.2f}", "currency": "USD"}



def _add_match_explanations(products, query):
    """Attach concise, deterministic reasons based only on returned product fields."""
    import re

    ignored = {
        "the", "and", "for", "with", "under", "below", "less", "than", "want",
        "need", "looking", "find", "show", "best", "good", "recommend", "buy",
        "please", "get", "some", "product", "products", "item", "items",
    }
    terms = [
        t for t in re.findall(r"[a-z0-9]+", (query or "").lower())
        if len(t) > 2 and t not in ignored and not t.isdigit()
    ]
    for product in products:
        fields = [
            str(product.get("name", "")),
            str(product.get("category", "")),
            str(product.get("description", "")),
            " ".join(str(x) for x in product.get("tags", [])),
            str(product.get("brand", "")),
        ]
        haystack = " ".join(fields).lower()
        matched = []
        for term in terms:
            if term in haystack and term not in matched:
                matched.append(term)
        reasons = []
        if matched:
            reasons.append("Matches your search: " + ", ".join(matched[:3]))
        category = product.get("category")
        if category:
            reasons.append("Category: " + str(category))
        if product.get("checkout_eligible"):
            reasons.append("Eligible for PayPilot demo checkout")
        else:
            reasons.append("External listing — checkout on the seller's site")
        product["why_recommended"] = " · ".join(reasons)
    return products


def _system_prompt():
    return (
        "You are PayPilot, a careful AI shopping and checkout agent. "
        "You MUST call search_catalog before recommending any product. "
        "Use the customer's requested product category and constraints; never recommend an unrelated item "
        "just because it is the first catalog result. If no relevant match is found, say so clearly and ask "
        "a useful follow-up. Never invent product names, prices, stock, ratings, IDs or merchant guarantees. "
        "Label DummyJSON products as sample/demo catalog data, not live retailer inventory. "
        "Label eBay results as marketplace listings and tell the customer to follow the listing link to buy "
        "from that seller; eBay items are not eligible for PayPilot checkout. "
        "Only use prepare_cart when the customer clearly asks to buy/add an eligible PayPilot or DummyJSON "
        "demo product. Do not add eBay items to PayPilot's cart. "
        "Never claim a payment has happened. PayPal Sandbox checkout requires the customer's explicit approval. "
        "When presenting search results, explain each match using only returned product fields; do not invent benefits. ""Keep replies concise, transparent and helpful."
    )


def run_agent(message, history=None):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        return fallback_agent(message)

    messages = [{"role": "system", "content": _system_prompt()}]
    for entry in (history or [])[-8:]:
        if entry.get("role") in ("user", "assistant") and isinstance(entry.get("content"), str):
            messages.append({"role": entry["role"], "content": entry["content"][:1500]})
    messages.append({"role": "user", "content": (message or "")[:2000]})

    products = []
    cart = None
    try:
        for _ in range(5):
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "tools": TOOLS,
                      "tool_choice": "auto", "temperature": 0.2},
                timeout=35,
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]["message"]
            messages.append(choice)
            calls = choice.get("tool_calls") or []
            if not calls:
                return {
                    "reply": choice.get("content") or "I can help you find something.",
                    "cart": cart, "products": products, "mode": "ai",
                }
            for call in calls:
                name = call["function"]["name"]
                args = json.loads(call["function"].get("arguments") or "{}")
                if name == "search_catalog":
                    products = _add_match_explanations(search_catalog(args.get("query", "")), args.get("query", ""))
                    output = {"products": products, "count": len(products)}
                elif name == "prepare_cart":
                    output = _prepare_cart(args)
                    if output.get("items"):
                        cart = output
                else:
                    output = {"error": "Unknown tool"}
                messages.append({
                    "role": "tool", "tool_call_id": call["id"],
                    "content": json.dumps(output, ensure_ascii=False),
                })
        return {
            "reply": "I found product options. Review the results and tell me which eligible item you want.",
            "cart": cart, "products": products, "mode": "ai",
        }
    except Exception:
        # External discovery remains available in deterministic fallback mode.
        return fallback_agent(message, mode="fallback")


def fallback_agent(message, mode="guided-demo"):
    products = _add_match_explanations(search_catalog(message), message)
    words = message.lower()
    buy_intent = any(x in words for x in (
        "buy", "checkout", "order", "purchase", "add to cart", "i want to get"
    ))
    if not products:
        return {
            "reply": (
                "I couldn't find a relevant match in the connected product sources. "
                "Try a product type or brand/model (for example, 'laptop', 'Android phone' or 'wireless headphones'). "
                "I won't substitute an unrelated product."
            ),
            "cart": None, "products": [], "mode": mode,
        }

    if buy_intent:
        eligible = next((p for p in products if p.get("checkout_eligible")), None)
        if eligible:
            cart = _prepare_cart({"items": [{"product_id": eligible["id"], "quantity": 1}]})
            reply = (
                f"I found **{eligible['name']}** for ${eligible['price']} in the "
                f"{eligible.get('source', 'connected catalog')}. I've prepared a demo checkout proposal. "
                "Review the item and total before explicitly approving PayPal Sandbox checkout."
            )
        else:
            cart = None
            reply = (
                "I found marketplace listings, but they must be purchased directly from the seller. "
                "Open a listing link below; I won't route an external seller's item through PayPilot checkout."
            )
    else:
        cart = None
        sources = sorted({p.get("source", "Connected catalog") for p in products})
        reply = (
            f"I found {len(products)} relevant product option(s) across {', '.join(sources)}. "
            "Review the product cards below. Tell me which eligible demo item you'd like to add to your proposal."
        )
    return {"reply": reply, "cart": cart, "products": products, "mode": mode}
