import sys
sys.path.insert(0, "src")
from fastapi.testclient import TestClient
from oneai_reach.api.main import app

client = TestClient(app)
response = client.post(
    "/api/v1/products",
    headers={"X-API-Key": "test"},
    json={
        "product_data": {
            "wa_number_id": "wa1",
            "name": "Test Product",
            "base_price_cents": 1000,
            "category": "electronics",
            "sku": "test-sku"
        }
    }
)
print(response.status_code)
print(response.json())
