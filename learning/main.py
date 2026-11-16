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

@app.get("/")
def home():
    page_path = Path(__file__).resolve().parent / "static" / "index.html"
    return FileResponse(page_path, media_type="text/html")

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
        conn.commit()
    finally:
        conn.close()
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
            "SELECT id, title, brand, size FROM items WHERE id = ?",
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
    return analyze_garment(photo_paths)

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
