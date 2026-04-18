import sys
sys.path.insert(0, "src")
from fastapi.testclient import TestClient
from oneai_reach.api.main import app

print(app.openapi()["paths"]["/api/v1/products"]["post"]["requestBody"]["content"]["application/json"]["schema"])
