import io
import json
import threading
import time
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.config import Settings
from app.main import make_app
from app.models import CompInput, Identification
from app.pricing import summarize
from app.providers import CompsAPI, Ollama, ProviderError
from app.store import Store, now

HEADERS = {"X-Vintagecat-Request": "1"}


@pytest.fixture
def env(tmp_path):
    settings = Settings(tmp_path, compsapi_key="test-key", monthly_search_limit=2)
    app = make_app(settings)
    with TestClient(app, headers=HEADERS) as client:
        yield app, client, settings


def photo_bytes(color="blue"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(buf, format="JPEG")
    return buf.getvalue()


def new_item(client):
    res = client.post("/api/items")
    assert res.status_code == 201
    return res.json()


def edit_payload(item, **changes):
    keys = ["version", "title", "brand", "model", "category", "size", "era", "condition", "notes", "cost", "asking_price", "status"]
    return dict({k: item[k] for k in keys}, **changes)


def wait_job(client, job_id):
    for _ in range(100):
        job = client.get("/api/jobs/" + job_id).json()
        if job["state"] not in ("queued", "running"):
            return job
        time.sleep(.01)
    raise AssertionError("Job failed to finish")


def comp(**changes):
    return dict({"id": "comp", "price": 50, "currency": "USD", "sold_date": date.today().isoformat(),
                 "matched": True, "evidence_type": "provider_reported"}, **changes)


def test_price_evidence_excludes_asking_currency_unreviewed_and_stale():
    result = summarize([comp(id="valid"), comp(id="asking", evidence_type="asking", price=900),
                        comp(id="foreign", currency="GBP", price=700), comp(id="unreviewed", matched=False),
                        comp(id="old", sold_date=(date.today()-timedelta(days=181)).isoformat())])
    assert result["count"] == 1 and result["median"] == 50
    assert len(result["excluded"]) == 4 and result["thin_sample"]
    assert result["tier"] == "provider_reported_sales"


def test_verified_and_empty_are_distinct():
    assert summarize([])["median"] is None
    assert summarize([comp(evidence_type="manually_verified")])["tier"] == "manually_verified_sales"


@pytest.mark.parametrize("patch", [{"price": float("nan")}, {"price": float("inf")}, {"price": -1},
                                  {"url": "javascript:alert(1)"}, {"sold_date": date.today()+timedelta(days=1)},
                                  {"sold_date": None}])
def test_invalid_evidence_is_rejected(patch):
    payload = dict(title="Example jacket", url="https://www.ebay.com/itm/123456", price=50,
                   sold_date=date.today(), evidence_type="manually_verified")
    payload.update(patch)
    with pytest.raises(ValidationError):
        CompInput(**payload)


def test_upload_deduplicates_preserves_original_and_rejects_bad_files(env):
    app, client, settings = env
    item = new_item(client)
    blob = photo_bytes()
    url = f"/api/items/{item['id']}/photos"
    res = client.post(url, files=[("files", ("tag.jpg", blob, "image/jpeg")), ("files", ("copy.jpg", blob, "image/jpeg"))])
    assert res.status_code == 200
    saved = res.json()
    assert len(saved["photos"]) == 1
    p = saved["photos"][0]
    assert (settings.data_dir / "photos" / (p["id"] + ".original")).read_bytes() == blob
    assert client.get(p["url"]).status_code == 200
    assert client.post(url, files={"files": ("fake.jpg", b"not an image", "image/jpeg")}).status_code == 400
    assert len(app.state.store.get(item["id"])["photos"]) == 1


def test_atomic_photo_batch_on_invalid_image(env):
    _, client, settings = env
    item = new_item(client)
    res = client.post(f"/api/items/{item['id']}/photos", files=[("files", ("real.jpg", photo_bytes(), "image/jpeg")),
                                                             ("files", ("bad.jpg", b"bad", "image/jpeg"))])
    assert res.status_code == 400
    assert list((settings.data_dir / "photos").iterdir()) == []


def test_optimistic_lock_preserves_edits_and_data_survives_reopen(env):
    _, client, settings = env
    item = new_item(client)
    url = "/api/items/" + item["id"]
    assert client.patch(url, json=edit_payload(item, title="My jacket")).status_code == 200
    assert client.patch(url, json=edit_payload(item, title="Stale edit")).status_code == 409
    reopened = Store(settings.data_dir / "vintagecat.sqlite3")
    assert reopened.get(item["id"])["title"] == "My jacket"


def test_match_review_and_identity_edit_invalidation(env):
    _, client, _ = env
    item = new_item(client)
    url = "/api/items/" + item["id"]
    payload = dict(title="Example jacket", url="https://www.ebay.com/itm/123456", price=50,
                   evidence_type="manually_verified", sold_date=date.today().isoformat())
    item = client.post(url+"/comps", json=payload).json()
    assert item["valuation"]["count"] == 0
    c = item["comps"][0]
    item = client.patch(url+"/comps/"+c["id"], json={"version": item["version"], "matched": True, "verified": True}).json()
    assert item["valuation"]["median"] == 50
    item = client.patch(url, json=edit_payload(item, brand="Different brand")).json()
    assert item["valuation"]["count"] == 0
    assert client.post(url+"/comps", json=payload).status_code == 409


def test_csrf_origin_and_host_guards(env):
    _, client, _ = env
    assert client.post("/api/items", headers={"X-Vintagecat-Request":""}).status_code == 403
    assert client.post("/api/items", headers={"Origin":"https://evil.example"}).status_code == 403
    assert client.get("/", headers={"Host":"evil.example"}).status_code == 400
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]


def test_job_failure_preserves_data_and_is_not_empty_market(env, monkeypatch):
    app, client, _ = env
    item = new_item(client)
    def fail(query):
        raise ProviderError("Provider timed out")
    monkeypatch.setattr(app.state.research, "search", fail)
    job = client.post(f"/api/items/{item['id']}/research", json={"query":"Carhartt jacket"}).json()
    assert wait_job(client, job["id"])["state"] == "failed"
    saved = app.state.store.get(item["id"])
    assert saved["research_history"] == [] and saved["title"] == item["title"]


def test_concurrent_job_dedup_and_analysis_never_clobbers_manual_edits(env, monkeypatch):
    app, client, _ = env
    item = new_item(client)
    url = "/api/items/" + item["id"]
    item = client.post(url+"/photos", files={"files": ("a.jpg", photo_bytes(), "image/jpeg")}).json()
    gate = threading.Event()
    def identify(images, notes):
        gate.wait(2)
        return {"result":{"title":"MODEL TITLE"},"model":"fixture","created_at":now()}
    monkeypatch.setattr(app.state.vision, "identify", identify)
    try:
        j1 = client.post(url+"/identify").json()
        j2 = client.post(url+"/identify").json()
        assert j1["id"] == j2["id"] and j2["reused"]
        assert client.patch(url, json=edit_payload(item, title="Human correction")).status_code == 200
    finally:
        gate.set()
    assert wait_job(client, j1["id"])["state"] == "succeeded"
    saved = client.get(url).json()
    assert saved["title"] == "Human correction" and saved["analysis"]["result"]["title"] == "MODEL TITLE"


def test_recovery_marks_interrupted_without_reissuing(env):
    app, _, _ = env
    with app.state.store.connect() as con:
        con.execute("INSERT INTO jobs VALUES('j','item','research','running','{}',NULL,?,NULL)", (now(),))
    app.state.store.recover()
    assert app.state.store.job("j")["state"] == "interrupted"


def test_comps_adapter_schema_cache_and_conservative_quota(env):
    app, _, settings = env
    calls = []
    def handler(req):
        calls.append(req)
        assert req.headers["x-api-key"] == "test-key"
        assert req.url.params["site"] == "US"
        assert req.url.params["days"] == "90"
        return httpx.Response(200, json={"ok":True,"items":[{"item_id":"123456789", "title":"Carhartt jacket",
            "price":50,"last_sold":now(),"best_offer":True}, {"item_id":"22222222", "title":"Bad row", "price":-5,"last_sold":now()}]})
    provider = CompsAPI(settings, app.state.store, httpx.MockTransport(handler))
    result = provider.search("Carhartt jacket")
    assert len(result["comps"]) == 1 and result["rejected_rows"] == 1
    assert result["comps"][0]["evidence_type"] == "provider_reported" and not result["comps"][0]["matched"]
    assert provider.search("Carhartt jacket")["cached"] and len(calls) == 1
    provider.search("Levis jeans")
    with pytest.raises(ProviderError, match="cap"):
        provider.search("Third query")
    assert len(calls) == 2


@pytest.mark.parametrize("status,body", [(429,{"error":"limit"}), (200,{"ok":False}), (200,{"ok":True,"items":[{}]})])
def test_provider_failures_never_become_empty_results(env, status, body):
    app, _, settings = env
    provider = CompsAPI(settings, app.state.store, httpx.MockTransport(lambda req:httpx.Response(status,json=body)))
    with pytest.raises(ProviderError):
        provider.search("Jacket")


def test_ollama_schema_images_and_invalid_output(env, tmp_path):
    _, _, settings = env
    path = tmp_path / "fixture.jpg"
    path.write_bytes(photo_bytes())
    def handler(req):
        payload = json.loads(req.content)
        assert payload["messages"][0]["images"]
        assert payload["format"]["properties"]["brand"]
        assert payload["stream"] is False
        return httpx.Response(200,json={"message":{"content":'{"title":"incomplete"}'}})
    provider = Ollama(settings, httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="invalid structured"):
        provider.identify([path], "")


def test_export_contains_records_but_no_credentials(env):
    _, client, _ = env
    item = new_item(client)
    response = client.get("/api/export")
    assert response.json()["items"][0]["id"] == item["id"]
    assert "test-key" not in response.text
    assert client.get("/api/status").json()["sold_data_configured"]


def test_asking_entry_cannot_be_relabelled_as_a_sale(env):
    _, client, _ = env
    item = new_item(client)
    url = "/api/items/"+item["id"]
    item = client.post(url+"/comps", json={"title":"Example", "url":"https://example.com/item", "price":100,
                  "evidence_type":"asking", "sold_date":date.today().isoformat()}).json()
    assert client.patch(url+"/comps/"+item["comps"][0]["id"], json={"version":item["version"],"matched":True,"verified":True}).status_code == 400
