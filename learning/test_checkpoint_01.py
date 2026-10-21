"""Acceptance checks for YOUR implementation. Expected to fail before you write it."""
from fastapi.testclient import TestClient
from learning.main import app, items

client = TestClient(app)


def test_create_and_read_garment():
    items.clear()
    response = client.post("/items", json={"title":"Brown work jacket", "brand":"Carhartt", "size":"L"})
    assert response.status_code == 201
    item = response.json()
    assert isinstance(item["id"], str) and item["id"]
    assert item["title"] == "Brown work jacket"
    assert item["brand"] == "Carhartt" and item["size"] == "L"
    assert client.get("/items/" + item["id"]).json() == item


def test_unknown_brand_and_size_remain_unknown():
    response = client.post("/items", json={"title":"Unidentified garment"})
    assert response.status_code == 201
    assert response.json()["brand"] is None
    assert response.json()["size"] is None


def test_invalid_title_is_rejected():
    for payload in ({}, {"title":""}, {"title":"x"*121}):
        assert client.post("/items", json=payload).status_code == 422


def test_missing_item_returns_404():
    assert client.get("/items/does-not-exist").status_code == 404


def test_identical_titles_get_different_ids():
    first = client.post("/items", json={"title":"Levis jeans"}).json()
    second = client.post("/items", json={"title":"Levis jeans"}).json()
    assert first["id"] != second["id"]
