"""Your hands-on build. Run: python -m uvicorn learning.main:app --reload --port 8001

Checkpoint 1: implement the item API in docs/LEARNING.md.
This starter intentionally does not implement the reference application's features.
"""
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(title="Vintagecat — my build")
items = {}


@app.get("/health")
def health():
    return {"status": "ok"}

# TODO 1: Define an ItemCreate model. See the contract in docs/LEARNING.md.
class ItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    brand: Optional[str] = Field(default=None)
    size: Optional[str] = Field(default=None)

# TODO 2: Implement POST /items (201): validate the body, create an ID, store and return the item.
@app.post("/items", status_code=201)
def create_item(item: ItemCreate):
    item_id = str(uuid4())
    item_data = item.model_dump()
    item_data["id"] = item_id
    items[item_id] = item_data
    return item_data

# TODO 3: Implement GET /items/{item_id}: return the stored item or HTTP 404.
@app.get("/items/{item_id}")
def get_item(item_id: str):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    return items[item_id]