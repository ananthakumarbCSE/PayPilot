"""Specialist-agent orchestration layer for PayPilot."""
import re
from decimal import Decimal, InvalidOperation

def _extract_budget(message):
    text=(message or "").lower().replace(",","")
    patterns=[
        r"(?:under|below|less than|max(?:imum)?|budget(?: of)?|up to)\s*[$₹]?\s*(\d+(?:\.\d{1,2})?)",
        r"[$₹]\s*(\d+(?:\.\d{1,2})?)",
    ]
    for pattern in patterns:
        m=re.search(pattern,text)
        if m:
            try:
                amount=Decimal(m.group(1)).quantize(Decimal("0.01"))
                if amount>0:return amount
            except (InvalidOperation,ValueError):pass
    return None

def _shopping_agent(result):
    products=result.get("products") if isinstance(result.get("products"),list) else []
    return {"agent":"Shopping Agent","status":"completed",
            "detail":f"Reviewed {len(products)} product result(s) from connected sources."}

def _budget_agent(result,message):
    budget=_extract_budget(message)
    products=result.get("products") if isinstance(result.get("products"),list) else []
    if budget is None:
        return {"agent":"Budget Agent","status":"skipped",
                "detail":"No explicit spending limit detected; no budget assumed."}
    affordable=0
    for p in products:
        try:
            price=Decimal(str(p.get("price","0")))
            eligible=p.get("currency","USD")=="USD" and price<=budget
            p["within_budget"]=eligible
            p["budget_note"]=(f"${budget-price:.2f} under budget" if eligible else
                              (f"${price-budget:.2f} over budget" if p.get("currency","USD")=="USD" else "Currency not comparable"))
            affordable+=int(eligible)
        except (InvalidOperation,ValueError,TypeError):
            p["within_budget"]=False;p["budget_note"]="Price unavailable"
    return {"agent":"Budget Agent","status":"completed",
            "detail":f"Checked {len(products)} option(s) against ${budget:.2f}; {affordable} within budget."}

def _trust_agent(result):
    products=result.get("products") if isinstance(result.get("products"),list) else []
    eligible=external=0
    for p in products:
        if p.get("checkout_eligible"):
            eligible+=1;p["trust_label"]="PayPilot demo checkout eligible"
        else:
            external+=1;p["trust_label"]="External listing — seller checkout only"
        if p.get("source_type")=="dummyjson_demo":
            p["inventory_notice"]="Sample catalog data; inventory not verified"
    return {"agent":"Trust Agent","status":"completed",
            "detail":f"Checked checkout boundaries: {eligible} eligible demo item(s), {external} external listing(s)."}

def orchestrate_result(result,message):
    trace=[_shopping_agent(result),_budget_agent(result,message),_trust_agent(result)]
    result["agent_trace"]=trace
    result["orchestration"]={"supervisor":"PayPilot Supervisor","status":"completed",
        "agents_completed":sum(x["status"]=="completed" for x in trace),"agents_total":len(trace)}
    return result


def _personalization_agent(result, preferences):
    preferences = preferences if isinstance(preferences, dict) else {}
    categories = preferences.get("categories", [])
    brands = preferences.get("brands", [])
    if not isinstance(categories, list): categories = []
    if not isinstance(brands, list): brands = []
    categories = [str(x).strip().lower()[:40] for x in categories if str(x).strip()][:8]
    brands = [str(x).strip().lower()[:40] for x in brands if str(x).strip()][:8]
    budget = preferences.get("max_budget")
    try:
        budget = Decimal(str(budget)) if budget not in (None, "") else None
        if budget is not None and (budget <= 0 or budget > Decimal("1000000")): budget = None
    except (InvalidOperation, ValueError, TypeError):
        budget = None

    products = result.get("products") if isinstance(result.get("products"), list) else []
    for product in products:
        haystack = " ".join([
            str(product.get("name", "")), str(product.get("category", "")),
            str(product.get("brand", "")), str(product.get("description", "")),
            " ".join(str(x) for x in product.get("tags", []))
        ]).lower()
        matched_categories = [x for x in categories if x in haystack]
        matched_brands = [x for x in brands if x in haystack]
        score = len(matched_categories) * 2 + len(matched_brands) * 3
        product["preference_score"] = score
        reasons = []
        if matched_categories: reasons.append("Preferred category: " + ", ".join(matched_categories[:2]))
        if matched_brands: reasons.append("Preferred brand: " + ", ".join(matched_brands[:2]))
        product["personalization_note"] = " · ".join(reasons) if reasons else "Matches your current search."
        if budget is not None:
            try:
                price = Decimal(str(product.get("price", "0")))
                product["within_saved_budget"] = product.get("currency", "USD") == "USD" and price <= budget
            except (InvalidOperation, ValueError, TypeError):
                product["within_saved_budget"] = False

    products.sort(key=lambda p: (
        -int(p.get("preference_score", 0)),
        not bool(p.get("within_saved_budget", True)) if budget is not None else False
    ))
    if categories or brands or budget is not None:
        detail = f"Applied {len(categories)} category and {len(brands)} brand preference(s)"
        if budget is not None: detail += f" with a ${budget:.2f} budget"
        detail += " to product ranking."
        status = "completed"
    else:
        detail = "No saved preferences; recommendations use the current search only."
        status = "skipped"
    return {"agent":"Personalization Agent","status":status,"detail":detail}

_original_orchestrate_result = orchestrate_result
def orchestrate_result(result, message, preferences=None):
    result = _original_orchestrate_result(result, message)
    result["agent_trace"].append(_personalization_agent(result, preferences or {}))
    result["orchestration"]["agents_completed"] = sum(
        1 for item in result["agent_trace"] if item["status"] == "completed"
    )
    result["orchestration"]["agents_total"] = len(result["agent_trace"])
    return result
