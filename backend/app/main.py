from pathlib import Path
import json
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rapidfuzz import fuzz

from app.models import Entity

app = FastAPI(title="Sanctions Entity Explorer")

ALIAS_PENALTY = 0.9
METADATA_PENALTY = 0.7
MIN_SCORE = 65
DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "sdn_sample.json"
entities: list[Entity] = []
entity_name_by_id: dict[str, str] = {}
IMO_PATTERN = re.compile(r"\bIMO\s*(\d{7})\b", re.IGNORECASE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchResult(Entity):
    search_score: float
    match_type: str
    collision_warning: str | None
    is_recent: bool


class SearchTerm(BaseModel):
    value: str
    match_type: str
    penalty: float


def normalize_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_imo_terms(remarks: str | None) -> list[str]:
    if not remarks:
        return []
    return [f"IMO {imo_number}" for imo_number in IMO_PATTERN.findall(remarks)]


def _build_search_terms(entity: Entity) -> list[SearchTerm]:
    linked_names = [
        entity_name_by_id[relation.target_id]
        for relation in entity.relations
        if relation.target_id in entity_name_by_id
    ]
    terms: list[SearchTerm] = [
        SearchTerm(value=entity.name, match_type="primary_name", penalty=1.0),
        *[
            SearchTerm(value=alias, match_type="alias", penalty=ALIAS_PENALTY)
            for alias in entity.aliases
        ],
        *[
            SearchTerm(value=imo_term, match_type="imo", penalty=ALIAS_PENALTY)
            for imo_term in _extract_imo_terms(entity.remarks)
        ],
        *[
            SearchTerm(value=linked_name, match_type="linked_entity", penalty=ALIAS_PENALTY)
            for linked_name in linked_names
        ],
        *[
            SearchTerm(value=country_code, match_type="country", penalty=METADATA_PENALTY)
            for country_code in entity.countries
        ],
        *[
            SearchTerm(value=program_name, match_type="program", penalty=METADATA_PENALTY)
            for program_name in entity.programs
        ],
    ]

    if entity.remarks:
        terms.append(
            SearchTerm(value=entity.remarks, match_type="remarks", penalty=METADATA_PENALTY)
        )
    return terms


def _score_entity(entity: Entity, normalized_query: str) -> tuple[float, str]:
    best_score = 0.0
    best_match_type = "unknown"
    for term in _build_search_terms(entity):
        normalized_term = normalize_text(term.value)
        if not normalized_term:
            continue
        raw_score = max(
            fuzz.WRatio(normalized_query, normalized_term),
            fuzz.partial_ratio(normalized_query, normalized_term),
        )
        weighted_score = raw_score * term.penalty
        if weighted_score > best_score:
            best_score = weighted_score
            best_match_type = term.match_type
    return best_score, best_match_type


def _build_collision_warning(entity: Entity) -> str | None:
    collisions = [
        entity_name_by_id[relation.target_id]
        for relation in entity.relations
        if relation.type == "name_collision" and relation.target_id in entity_name_by_id
    ]
    if not collisions:
        return None
    return f"Potential name collision with: {', '.join(collisions)}"


def _is_recent(entity: Entity) -> bool:
    return 2023 <= entity.list_date.year <= 2026


@app.on_event("startup")
def load_entities() -> None:
    global entities, entity_name_by_id
    raw_entities = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    entities = [Entity.model_validate(item) for item in raw_entities]
    entity_name_by_id = {entity.id: entity.name for entity in entities}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/entities", response_model=list[Entity])
def list_entities() -> list[Entity]:
    return entities


@app.get("/api/search", response_model=list[SearchResult])
def search_entities(q: str) -> list[SearchResult]:
    normalized_query = normalize_text(q)
    if not normalized_query:
        return []

    results: list[SearchResult] = []
    for entity in entities:
        score, match_type = _score_entity(entity, normalized_query)
        if score < MIN_SCORE:
            continue
        results.append(
            SearchResult(
                **entity.model_dump(),
                search_score=round(score, 2),
                match_type=match_type,
                collision_warning=_build_collision_warning(entity),
                is_recent=_is_recent(entity),
            )
        )

    results.sort(key=lambda item: item.search_score, reverse=True)
    return results
