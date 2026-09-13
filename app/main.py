from fastapi import FastAPI
from app.telemetry import configure_tracing

app = FastAPI()
configure_tracing(app)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/hello")
def hello():
    return {"message": "Hello from my homelab"}


@app.get("/items/{id}")
def get_item(id: int):
    return {"id": id, "name": f"Item {id}"}

