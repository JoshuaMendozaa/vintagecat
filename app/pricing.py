from datetime import date
from statistics import median


def summarize(comps, today=None):
    """Observed comparable prices, never a calibrated prediction or market-wide demand score."""
    today = today or date.today()
    accepted, excluded = [], []
    for comp in comps:
        reasons = []
        if not comp.get("matched"):
            reasons.append("Match not reviewed")
        if comp.get("evidence_type") not in ("provider_reported", "manually_verified"):
            reasons.append("Not sold-price evidence")
        if comp.get("currency") != "USD":
            reasons.append("Currency is not USD; no automatic conversion")
        try:
            age = (today - date.fromisoformat(comp["sold_date"][:10])).days
            if age < 0 or age > 180:
                reasons.append("Sale outside the 180-day comparison window")
        except (ValueError, KeyError, TypeError):
            reasons.append("Missing or invalid sold date")
        if reasons:
            excluded.append({"id": comp["id"], "reasons": reasons})
        else:
            accepted.append(comp)
    if not accepted:
        return {"tier": "no_reviewed_sales", "count": 0, "median": None, "low": None, "high": None,
                "excluded": excluded, "note": "No usable, reviewed sold comps. This does not establish rarity or lack of demand."}
    prices = [c["price"] for c in accepted]
    verified = sum(c["evidence_type"] == "manually_verified" for c in accepted)
    return {"tier": "manually_verified_sales" if verified == len(accepted) else "provider_reported_sales",
            "count": len(prices), "verified_count": verified,
            "median": round(median(prices), 2), "low": min(prices), "high": max(prices),
            "thin_sample": len(prices) < 5, "excluded": excluded,
            "note": "Observed item-price range, excluding shipping and taxes. Not a forecast or recommended asking price."
                    + (" Small sample: fewer than five reviewed sales." if len(prices) < 5 else "")}

