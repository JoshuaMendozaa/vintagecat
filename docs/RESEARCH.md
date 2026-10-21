# Provider and model decision record

Research date: October 17, 2026. These are published vendor statements, not independent validation.

## Chosen first interfaces

**Ollama local vision:** REST `/api/chat` accepts base64 image arrays and a JSON schema in `format`. Vintagecat validates the returned content with Pydantic; a schema is not factual verification. Model temperature is 0; context is 8192; latency and prompt version are retained. Selected trial: `qwen3-vl:8b`; optional smaller local trial: `qwen3-vl:4b`. No Hugging Face runtime is necessary for this vertical slice; interchangeable model experiments can be added after a baseline.

- https://docs.ollama.com/capabilities/vision
- https://docs.ollama.com/capabilities/structured-outputs
- https://ollama.com/library/qwen3-vl:8b

**CompsAPI candidate:** documented API key header, dates, price, unit count and source links; advertised free tier of 100 searches/month, Starter $9/month. The initial adapter pins US and 90 days. Its stated price field is average paid per unit, including accepted offers. Vintagecat labels that assertion provider-reported, not verified. Marketplace reporting quirks and agreement with actual records require a trial.

- https://compsapi.com/docs
- https://compsapi.com/

**Not resolved:** live API access; garment retrieval quality; Best Offer accuracy; provider's data rights and downstream display/storage permissions. A documented API is not proof of marketplace authorization. Do not infer a licensing guarantee from this implementation. Start with manual comps if access or use terms are unclear. No credentials, account creation or purchase was performed during development.

## Other routes investigated

- eBay Marketplace Insights: official sold-data interface remains restricted to existing approved access according to eBay's Buy API field-filter documentation. An ordinary eBay developer key is not sufficient.
  https://www.developer.ebay.com/api-docs/buy/static/ref-buy-browse-filters.html
- eBay Product Research: useful human reference including accepted Best Offers; seller-facing access is separate from application API access.
  https://www.ebay.com/help/selling/selling-tools/research?id=4853
- SearchAPI eBay: documentation states sold/completed filters are no longer supported because it retrieves public pages only. Do not wire it up as a verified sold feed.
  https://www.searchapi.org/docs/ebay-search-api
- eBay Sold Listings API: another documented third-party candidate. No live test, schema validation or licensing review completed; not integrated.
  https://ebaysoldlistingsapi.com/docs

## What this version intentionally does not claim

- No fabricated comparable URLs, automatic authentication, demand score or rarity score.
- No precise sale-speed prediction or probability-calibrated price interval. The summary range is simply the observed minimum and maximum of reviewed eligible rows.
- No autonomous match approval. Keyword similarity alone cannot establish garment equivalence.
- No automatic historical backfill, model training on marketplace content or competitor-output harvesting.
- No automatic publishing. Research and seller integrations are separate workstreams.

## Evaluation gate

For each of 20–30 garments, collect clear photos and a manually checked identity. Test the same photo set across model configurations. Use independently selected held-out garments for the final comparison. Check each candidate comp's actual relevance, displayed/transaction price status, date, currency and duplicates. Report abstentions as well as successes. Do not grade the model against another model's unverified answer.

For eventual resale predictions, record the predicted range before listing, actual asking price, sale date, actual transaction amount and fees. An unsold item is not a sale-price observation. A self-chosen low asking price can cap the observed sale, so a sale at asking does not prove the predicted market value. Separate observed comp summaries from genuine forecasts.
