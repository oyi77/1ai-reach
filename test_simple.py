from fastapi import FastAPI, Depends
from pydantic import BaseModel
from fastapi.testclient import TestClient

app = FastAPI()

class Item(BaseModel):
    name: str

@app.post("/items")
def create_item(item: Item):
    return item

client = TestClient(app)
resp = client.post("/items", json={"name": "test"})
print(resp.json())
