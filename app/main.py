import hashlib
import io
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import ROOT, get_settings
from .models import CompInput, CompReview, ItemEdit, ResearchRequest
from .pricing import summarize
from .providers import CompsAPI, Ollama, ProviderError
from .store import Store, now

logger = logging.getLogger("vintagecat")
MAX_PHOTOS = 12
MAX_BYTES = 15 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000


def identity(item):
    return {k: item.get(k) for k in ("title", "brand", "model", "category", "size", "era", "condition", "notes")}


def make_app(settings=None):
    settings = settings or get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    photos_dir = settings.data_dir / "photos"
    photos_dir.mkdir(exist_ok=True)
    store = Store(settings.data_dir / "vintagecat.sqlite3")
    vision = Ollama(settings)
    research = CompsAPI(settings, store)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vintagecat")

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        executor.shutdown(wait=True, cancel_futures=True)

    app = FastAPI(title="Vintagecat local research", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.vision, app.state.research = store, vision, research
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.middleware("http")
    async def local_safety(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("x-vintagecat-request") != "1":
                return JSONResponse({"detail": "Same-origin request header required"}, status_code=403)
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
            try:
                if int(request.headers.get("content-length", "0")) > 70 * 1024 * 1024:
                    return JSONResponse({"detail": "Upload fewer than 70 MB at a time"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        result = await call_next(request)
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        result.headers["Cache-Control"] = "no-store"
        return result

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse({"detail": "Item or job not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    def detail(item_id):
        item = store.get(item_id)
        item["valuation"] = summarize(item["comps"])
        item["analysis_stale"] = bool(item.get("analysis") and item["analysis"].get("photo_ids") != [p["id"] for p in item["photos"]])
        item["estimate_stale"] = bool(item.get("estimate") and item["estimate"].get("identity") != identity(item))
        with store.connect() as con:
            item["jobs"] = [dict(r) for r in con.execute("SELECT id, kind, state, error, created_at, finished_at FROM jobs WHERE item_id=? ORDER BY created_at DESC LIMIT 20", (item_id,))]
        return item

    @app.get("/api/status")
    def status():
        with store.connect() as con:
            row = con.execute("SELECT calls FROM usage WHERE month=?", (now()[:7],)).fetchone()
        return {"mode": "local", "model": settings.model, "sold_data_configured": bool(settings.compsapi_key),
                "searches_used": row[0] if row else 0, "search_limit": settings.monthly_search_limit,
                "publishing": "not_implemented"}

    @app.get("/api/ollama/check")
    def check_ollama():
        import httpx
        try:
            with httpx.Client(timeout=3, trust_env=False) as client:
                response = client.get(settings.ollama_url + "/api/tags")
                response.raise_for_status()
                names = [m["name"] for m in response.json().get("models", [])]
            return {"reachable": True, "model_ready": settings.model in names, "models": names}
        except (httpx.HTTPError, ValueError, KeyError):
            return {"reachable": False, "model_ready": False, "models": []}

    @app.get("/api/items")
    def items():
        return store.all()

    @app.post("/api/items", status_code=201)
    def create_item():
        item_id = uuid4().hex
        item = ItemEdit(version=1).model_dump(exclude={"version"})
        item.update(id=item_id, sku="VC-" + item_id[:8].upper(), created_at=now(), updated_at=now(),
                    photos=[], comps=[], analysis=None, estimate=None, research_history=[])
        store.create(item)
        return detail(item_id)

    @app.get("/api/items/{item_id}")
    def get_item(item_id: str):
        return detail(item_id)

    @app.patch("/api/items/{item_id}")
    def edit_item(item_id: str, edit: ItemEdit):
        def apply(data):
            changed = identity(data) != identity(edit.model_dump())
            data.update(edit.model_dump(exclude={"version"}))
            if changed:
                for comp in data["comps"]:
                    comp["matched"] = False
        store.mutate(item_id, apply, edit.version)
        return detail(item_id)

    @app.post("/api/items/{item_id}/photos")
    async def upload_photos(item_id: str, files: list[UploadFile] = File(...)):
        item = store.get(item_id)
        if len(files) + len(item["photos"]) > MAX_PHOTOS:
            raise HTTPException(400, "Up to 12 photos per garment")
        prepared = []
        known_hashes = {p["sha256"] for p in item["photos"]}
        try:
            for upload in files:
                blob = await upload.read(MAX_BYTES + 1)
                if len(blob) > MAX_BYTES:
                    raise HTTPException(413, "Each photo must be 15 MB or smaller")
                digest = hashlib.sha256(blob).hexdigest()
                if digest in known_hashes:
                    continue
                try:
                    with Image.open(io.BytesIO(blob)) as im:
                        if im.format not in ("JPEG", "PNG", "WEBP") or im.width * im.height > 40_000_000:
                            raise ValueError("Unsupported image")
                        im = ImageOps.exif_transpose(im).convert("RGB")
                        im.thumbnail((1800, 1800))
                        normalized = io.BytesIO()
                        im.save(normalized, format="JPEG", quality=90)
                except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                    raise HTTPException(400, "Use JPG, PNG or WebP under 40 megapixels. Convert HEIC to JPG first.") from exc
                photo_id = uuid4().hex
                photo = {"id": photo_id, "sha256": digest, "name": Path(upload.filename or "photo").name[:200],
                         "url": f"/api/photos/{photo_id}", "position": len(item["photos"]) + len(prepared),
                         "created_at": now()}
                prepared.append((photo, blob, normalized.getvalue()))
                known_hashes.add(digest)
            for photo, blob, normalized in prepared:
                (photos_dir / (photo["id"] + ".original")).write_bytes(blob)
                (photos_dir / (photo["id"] + ".jpg")).write_bytes(normalized)
            def append(data):
                if len(data["photos"]) + len(prepared) > MAX_PHOTOS:
                    raise ValueError("Photo limit changed; reload the item")
                data["photos"].extend(p[0] for p in prepared)
            store.mutate(item_id, append, item["version"])
        except Exception:
            for photo, _, _ in prepared:
                (photos_dir / (photo["id"] + ".original")).unlink(missing_ok=True)
                (photos_dir / (photo["id"] + ".jpg")).unlink(missing_ok=True)
            raise
        return detail(item_id)

    class PhotoOrder(BaseModel):
        version: int
        ids: list[str]

    @app.post("/api/items/{item_id}/photo-order")
    def photo_order(item_id: str, order: PhotoOrder):
        def apply(data):
            by_id = {p["id"]: p for p in data["photos"]}
            if len(order.ids) != len(by_id) or set(order.ids) != set(by_id):
                raise HTTPException(400, "Photo order must include each photo exactly once")
            data["photos"] = [dict(by_id[pid], position=i) for i, pid in enumerate(order.ids)]
        store.mutate(item_id, apply, order.version)
        return detail(item_id)

    @app.get("/api/photos/{photo_id}")
    def photo(photo_id: str):
        if len(photo_id) != 32 or any(c not in "0123456789abcdef" for c in photo_id):
            raise HTTPException(404)
        path = photos_dir / (photo_id + ".jpg")
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/items/{item_id}/comps", status_code=201)
    def add_comp(item_id: str, comp: CompInput):
        if comp.evidence_type == "provider_reported":
            raise HTTPException(400, "Manual entries must use unknown, asking, or manually_verified evidence")
        record = comp.model_dump(mode="json")
        record.update(id=uuid4().hex, source="Manual", source_id=comp.url, matched=False,
                      retrieved_at=now(), flags=[], original_evidence="unknown" if comp.evidence_type == "manually_verified" else comp.evidence_type)
        def apply(data):
            if any(c["url"].rstrip("/") == comp.url.rstrip("/") for c in data["comps"]):
                raise HTTPException(409, "That source URL is already attached")
            data["comps"].append(record)
        store.mutate(item_id, apply)
        return detail(item_id)

    @app.patch("/api/items/{item_id}/comps/{comp_id}")
    def review_comp(item_id: str, comp_id: str, review: CompReview):
        def apply(data):
            comp = next((c for c in data["comps"] if c["id"] == comp_id), None)
            if comp is None:
                raise KeyError(comp_id)
            if review.verified and (not comp["sold_date"] or comp["original_evidence"] == "asking"):
                raise HTTPException(400, "Asking-price entries cannot be confirmed as sales; add the actual sale separately")
            comp["matched"] = review.matched
            comp["evidence_type"] = "manually_verified" if review.verified else comp["original_evidence"]
        store.mutate(item_id, apply, review.version)
        return detail(item_id)

    def run_job(job_id, snapshot, kind, payload):
        with store.connect() as con:
            con.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
        try:
            if kind == "identify":
                result = vision.identify([photos_dir / (p["id"] + ".jpg") for p in snapshot["photos"]], snapshot["notes"])
                result["photo_ids"] = [p["id"] for p in snapshot["photos"]]
                result["input_version"] = snapshot["version"]
                store.mutate(snapshot["id"], lambda data: data.update(analysis=result))
            elif kind == "estimate":
                result = vision.estimate(snapshot)
                result["identity"] = identity(snapshot)
                store.mutate(snapshot["id"], lambda data: data.update(estimate=result))
            else:
                result = research.search(payload["query"])
                def merge(data):
                    existing = {c["url"].rstrip("/") for c in data["comps"]}
                    data["comps"].extend(c for c in result["comps"] if c["url"].rstrip("/") not in existing)
                    data["research_history"].append({k: v for k, v in result.items() if k != "comps"})
                store.mutate(snapshot["id"], merge)
            with store.connect() as con:
                con.execute("UPDATE jobs SET state='succeeded', finished_at=? WHERE id=?", (now(), job_id))
        except Exception as exc:
            # Never expose credentials, request headers, vendor response bodies or paths in browser errors.
            message = str(exc) if isinstance(exc, ProviderError) else "Job failed unexpectedly. Existing item data was preserved."
            logger.warning("job_failed id=%s kind=%s exception=%s", job_id, kind, type(exc).__name__)
            with store.connect() as con:
                con.execute("UPDATE jobs SET state='failed', error=?, finished_at=? WHERE id=?", (message, now(), job_id))

    def enqueue(item_id, kind, payload):
        item = store.get(item_id)
        if kind == "identify" and not item["photos"]:
            raise HTTPException(400, "Upload garment photos first")
        if kind == "estimate" and (not item["category"] or item["title"] == "Untitled garment"):
            raise HTTPException(400, "Review and save the item title and category first")
        if kind == "research" and not settings.compsapi_key:
            raise HTTPException(409, "Configure a sold-data key locally, or attach manually researched comps")
        job_id = uuid4().hex
        try:
            with store.connect() as con:
                con.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (job_id, item_id, kind, "queued", json.dumps(payload), None, now(), None))
        except sqlite3.IntegrityError:
            with store.connect() as con:
                row = con.execute("SELECT id FROM jobs WHERE item_id=? AND kind=? AND state IN ('queued','running')", (item_id, kind)).fetchone()
            if row:
                return {"id": row[0], "reused": True}
            raise
        executor.submit(run_job, job_id, item, kind, payload)
        return {"id": job_id, "reused": False}

    @app.post("/api/items/{item_id}/identify", status_code=202)
    def identify_item(item_id: str):
        return enqueue(item_id, "identify", {})

    @app.post("/api/items/{item_id}/estimate", status_code=202)
    def estimate_item(item_id: str):
        return enqueue(item_id, "estimate", {})

    @app.post("/api/items/{item_id}/research", status_code=202)
    def research_item(item_id: str, query: ResearchRequest):
        return enqueue(item_id, "research", query.model_dump())

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.job(job_id)
        job.pop("payload")
        return job

    @app.get("/api/export")
    def export():
        return Response(json.dumps({"schema_version": 1, "exported_at": now(), "items": store.all()}, indent=2),
                        media_type="application/json", headers={"Content-Disposition": 'attachment; filename="vintagecat-catalogue.json"'})

    app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app" / "static" / "index.html")

    return app


app = make_app()
