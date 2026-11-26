from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from fastapi import UploadFile
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from pathlib import Path
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from learning.db import get_db_connection, init_db
from learning.db import init_db, get_db_connection
from learning.vision import analyze_garment, GarmentAnalysis
import json
from learning.listings import generate_listing_drafts, ListingDrafts, ListingEdits
from learning.pricing import SoldComparable, PriceSummary, summarize_prices

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)  # Ensure the upload directory exists   

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # Initialize the database schema on startup
    yield

app = FastAPI(lifespan=lifespan, title="Vintagecat — my build")
items = {}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


@app.get("/health")
def health():
    return {"status": "ok"}
class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    brand: Optional[str] = Field(default=None)
    size: Optional[str] = Field(default=None)
    color: Optional[str] = Field(default=None)

class ItemReview(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    brand: str | None
    size: str | None
    color: str | None
    condition_notes: list[str]

@app.get("/")
def home():
    page_path = Path(__file__).resolve().parent / "static" / "index.html"
    return FileResponse(page_path, media_type="text/html")

@app.put("/items/{item_id}/review")
def save_item_review(item_id: str, review: ItemReview):
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            UPDATE items
            SET title = ?, brand = ?, size = ?, color = ?, condition_notes = ?,
            listing_drafts_json = NULL
            WHERE id = ?
            """,
            (
                review.title,
                review.brand,
                review.size,
                review.color,
                json.dumps(review.condition_notes),
                item_id
            ),
        )

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="item not found")
        conn.commit()
    finally:
        conn.close()
    return {"id": item_id, **review.model_dump()}

@app.put("/items/{item_id}/listing-drafts", response_model=ListingDrafts)
def save_listing_edits(item_id: str, edits: ListingEdits):
    conn = get_db_connection()
    try:
        row = conn.execute(
            """SELECT listing_drafts_json FROM items WHERE id = ?""",
            (item_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Item not found")
        if row["listing_drafts_json"] is None:
            raise HTTPException(status_code=409, detail="Generate drafts before saving edits")

        drafts_json = row["listing_drafts_json"]
        saved_drafts = json.loads(drafts_json)
        saved_drafts.update(edits.model_dump())

        conn.execute(
            "UPDATE items SET listing_drafts_json = ? WHERE id = ?",
            (json.dumps(saved_drafts), item_id),
        )
        conn.commit()
    finally:
        conn.close()

    return saved_drafts

    

@app.post("/items/{item_id}/listing-drafts", response_model=ListingDrafts)
def create_listing_drafts(item_id: str):
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT title, brand, size, color, condition_notes, analysis_json
            FROM items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")

    reviewed_details = dict(row)
    analysis_json = reviewed_details.pop("analysis_json")

    reviewed_details["condition_notes"] = json.loads(
        reviewed_details["condition_notes"]
    )

    analysis = (
        json.loads(analysis_json) if analysis_json is not None else None
    )

    drafts = generate_listing_drafts(reviewed_details, analysis)

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "UPDATE items SET listing_drafts_json = ? WHERE id = ?",
            (drafts.model_dump_json(), item_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")

        conn.commit()
    finally:
        conn.close()

    return drafts   

@app.post("/items", status_code=201)
def create_item(item: ItemCreate):
    item_id = str(uuid4())
    item_data = item.model_dump()
    item_data["id"] = item_id
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO items (id, title, brand, size) VALUES (?, ?, ?, ?)",
            (item_id, item_data["title"], item_data.get("brand"), item_data.get("size"))
        )
        row = conn.commit()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")

    return item_data


    

@app.get("/items")
def list_items():
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, brand, size FROM items"
        ).fetchall()
    finally:
        conn.close()

    return [dict(row) for row in rows]


@app.get("/items/{item_id}")
def get_item(item_id: str):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT id, title, brand, size, color, condition_notes, analysis_json, listing_drafts_json FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        photo_rows = conn.execute(
            "SELECT id, filename, bytes_received FROM photos WHERE item_id = ?",
            (item_id,),
        ).fetchall()
    finally:
        conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    
    item_data = dict(row)

    listing_drafts_json = item_data.pop("listing_drafts_json")
    item_data["listing_drafts"] = (
        json.loads(listing_drafts_json) if listing_drafts_json is not None else None
    )
    

    item_data["condition_notes"] = json.loads(item_data["condition_notes"])

    analysis_json = item_data.pop("analysis_json")
    item_data["analysis"] = (
        json.loads(analysis_json) if analysis_json is not None else None
    )

    item_data["photos"] = [dict(photo_row) for photo_row in photo_rows]
    return item_data

@app.post("/items/{item_id}/photos")
def create_photos(item_id: str, photo: UploadFile):
    conn = get_db_connection()
    try:
        item_row = conn.execute(
            "SELECT id FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
    finally:
        conn.close()
    if item_row is None:
        raise HTTPException(status_code=404, detail="Item not found in database")

    contents = photo.file.read(MAX_PHOTO_BYTES + 1)
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Photo is empty")
    if len(contents) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo exceeds maximum size of 5MB")
    try:
        with Image.open(BytesIO(contents)) as image:
            image.verify()  # Verify that it's a valid image
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image")
    photo_id = str(uuid4())
    photo_path = UPLOAD_DIR / photo_id

    conn = get_db_connection()
    try:
        photo_path.write_bytes(contents)
        conn.execute(
            "INSERT INTO photos (id, item_id, filename, bytes_received) VALUES (?, ?, ?, ?)",
            (photo_id, item_id, photo.filename, len(contents))
        )
        conn.commit()
    except Exception:
        conn.rollback()
        photo_path.unlink(missing_ok=True)  # Remove the file if DB insert fails
        raise 
    finally:
        conn.close()

    return {"id": photo_id, "filename": photo.filename, "bytes_received": len(contents)}

@app.post("/items/{item_id}/analyze", response_model=GarmentAnalysis)
def analyze_item(item_id: str):
    conn = get_db_connection()
    try:
        garment = conn.execute(
            "SELECT id FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        photo_rows = conn.execute(
            "SELECT id FROM photos WHERE item_id = ?",
            (item_id,),
        ).fetchall()
    finally:
        conn.close()

    if garment is None:
        raise HTTPException(
            status_code=404, 
            detail="Item not found in database"
        )
    if not photo_rows:
        raise HTTPException(
            status_code=400,
            detail="Upload photos before analyzing this garment",
        )
    photo_paths = [UPLOAD_DIR / photo_row["id"] for photo_row in photo_rows]
    for path in photo_paths:
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"A saved photo file is missing",
            )
    analysis = analyze_garment(photo_paths)

    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE items SET analysis_json = ? WHERE id = ?",
            (analysis.model_dump_json(), item_id),
        )
        conn.commit()
    finally:
        conn.close()

    return analysis

@app.get("/items/{item_id}/photos/{photo_id}")
def get_photo(item_id: str, photo_id: str):
    conn = get_db_connection()
    try:
        photo_data = conn.execute(
            "SELECT id, filename, bytes_received FROM photos WHERE id = ? AND item_id = ?",
            (photo_id, item_id),
        ).fetchone()
    finally:
        conn.close()

    photo_path = UPLOAD_DIR / photo_data["id"]

    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Photo file not found")

    with Image.open(photo_path) as image:
        media_type = Image.MIME.get(image.format or "", "application/octet-stream")

    return FileResponse(photo_path, media_type=media_type)

@app.post("/items/{item_id}/sold-comparables", status_code=201)
def create_sold_comparable(item_id: str, sold_comparable: SoldComparable):
    conn = get_db_connection()
    try:
        item = conn.execute(
            "SELECT id FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")

        sold_on = sold_comparable.sold_on
        sold_on_text = sold_on.isoformat() if sold_on is not None else None
        comparable_id = str(uuid4())
        cursor = conn.execute(
            """INSERT INTO sold_comparables (id, item_id, title, source_url, currency, sold_price_cents, sold_on)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id, source_url) DO NOTHING""",
            (comparable_id, item_id, sold_comparable.title, sold_comparable.source_url, sold_comparable.currency, sold_comparable.sold_price_cents, sold_on_text)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="Sold comparable already exists")
        conn.commit()
    finally:
        conn.close()
    return {"id": comparable_id, "item_id": item_id, **sold_comparable.model_dump()}

@app.get("/items/{item_id}/price-summary", response_model=PriceSummary)
def get_item_price(item_id: str, currency: str = "USD"):
    conn = get_db_connection()
    try:
        item = conn.execute(
            """SELECT id FROM items WHERE id = ?""",
            (item_id,)
        ).fetchone()
        if item is None:
            raise HTTPException(status_code=404, detail="Item not found")

        rows = conn.execute(
            """SELECT title, source_url, sold_price_cents, currency, sold_on
            FROM sold_comparables
            WHERE item_id = ?
            """,
            (item_id,)
        ).fetchall()
    finally:
        conn.close()
    comps = [SoldComparable(**dict(row)) for row in rows]
    return summarize_prices(comps, currency)

    