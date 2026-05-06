from pathlib import Path
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import Entity

app = FastAPI(title="Sanctions Entity Explorer")

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "sdn_sample.json"
entities: list[Entity] = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def load_entities() -> None:
    global entities
    raw_entities = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    entities = [Entity.model_validate(item) for item in raw_entities]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/entities", response_model=list[Entity])
def list_entities() -> list[Entity]:
    return entities
