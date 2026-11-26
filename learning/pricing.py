from pydantic import BaseModel
from datetime import date
from statistics import median

class SoldComparable(BaseModel):
    title: str
    source_url: str
    sold_price_cents: int
    currency: str
    sold_on: date | None = None

class PriceSummary(BaseModel):
    currency: str
    comp_count: int
    median_sold_price_cents: float | None

def prices_in_currency(comps: list[SoldComparable], currency: str) -> list[int]:
    prices_cents = []
    for comp in comps:
        if comp.currency == currency:
            prices_cents.append(comp.sold_price_cents)
    return prices_cents

def median_sold_price_cents(comps: list[SoldComparable], currency: str) -> float | None:
    prices = prices_in_currency(comps, currency)
    if not prices:
        return None
    return median(prices)

def summarize_prices(comps: list[SoldComparable], currency: str) -> PriceSummary:
    prices = prices_in_currency(comps, currency)
    return PriceSummary(
        currency=currency,
        comp_count=len(prices),
        median_sold_price_cents=median(prices) if prices else None
    )

def build_comp_query(title: str, brand: str | None) -> str:
    clean_title = title.strip()
    clean_brand = (brand or "").strip()

    if not clean_brand or clean_brand.casefold() in clean_title.casefold():
        return clean_title
    return f"{clean_brand} {clean_title}"