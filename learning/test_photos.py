from fastapi.testclient import TestClient
from learning.main import app, items
from io import BytesIO
from PIL import Image

client = TestClient(app)

def test_upload_to_missing_item():
    response = client.post(
        "/items/does-not-exist/photos",
        files={"photo": ("test.png", b"test bytes", "image/png")}   
    )
    assert response.status_code == 404

def test_empty_photo_is_rejected():
    create_response = client.post(
        "/items", json={"title": "Test Jacket"}
    )
    item_id = create_response.json()["id"]

    response = client.post(
        f"/items/{item_id}/photos",
        files={"photo": ("empty.png", b"", "image/png")}
    )
    assert response.status_code == 400

def test_oversized_photo_is_rejected():
    create_response = client.post(
        "/items", json={"title": "Test Jacket"}
    )
    item_id = create_response.json()["id"]

    oversized_content = b"a" * (5 * 1024 * 1024 + 1)  # 5MB + 1 byte
    response = client.post(
        f"/items/{item_id}/photos",
        files={"photo": ("oversized.png", oversized_content, "image/png")}
    )
    assert response.status_code == 413

def test_valid_photo_is_accepted():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buffer, format="PNG")
    photo_bytes = buffer.getvalue()

    create_response = client.post(
        "/items", json={"title": "Test Jacket"}
    )
    item_id = create_response.json()["id"]

    response = client.post(
        f"/items/{item_id}/photos",
        files={"photo": ("test.png", photo_bytes, "image/png")}
    )

    assert response.status_code == 200
    assert response.json()["bytes_received"] == len(photo_bytes)