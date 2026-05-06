from pathlib import Path
import json
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models import Entity
from app.services.search_service import (
    EntityScoreResult,
    SearchTerm,
    build_search_terms,
    normalize_text,
    score_entity_fields,
)

app = FastAPI(title="Sanctions Entity Explorer")

ALIAS_PENALTY = 0.9
METADATA_PENALTY = 0.7
MIN_SCORE = 20
DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "sdn_sample.json"
entities: list[Entity] = []
entity_name_by_id: dict[str, str] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchResult(Entity):
    search_score: float
    matched_via: str
    match_type: str
    matched_field: str
    matched_value: str
    collision_warning: str | None
    is_recent: bool


def _build_search_terms(entity: Entity) -> list[SearchTerm]:
    return build_search_terms(entity, entity_name_by_id, ALIAS_PENALTY, METADATA_PENALTY)


def _score_entity(entity: Entity, raw_query: str) -> EntityScoreResult:
    normalized_query = normalize_text(raw_query)
    query_tokens = normalized_query.split()
    base_result = score_entity_fields(
        query=raw_query,
        query_tokens=query_tokens,
        entity=entity,
        search_terms=_build_search_terms(entity),
    )

    final_score = round(base_result.score, 2)
    print(f"[search_score] entity={entity.id} final={final_score}")
    return EntityScoreResult(
        score=final_score,
        matched_via=base_result.matched_via,
        match_type=base_result.match_type,
        matched_field=base_result.matched_field,
        matched_value=base_result.matched_value,
    )


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


def _extract_id_query(raw_query: str) -> str | None:
    normalized = raw_query.strip().upper()
    if re.fullmatch(r"SDN-\d{5}", normalized):
        return normalized
    return None


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

    id_query = _extract_id_query(q)
    if id_query:
        id_results: list[SearchResult] = []
        for entity in entities:
            score = 0.0
            matched_via = "none"
            matched_field = "none"
            matched_value = ""

            if entity.id.upper() == id_query:
                score = 100.0
                matched_via = "ID"
                matched_field = "id"
                matched_value = entity.id
            else:
                relation_hit = any(relation.target_id.upper() == id_query for relation in entity.relations)
                remarks_hit = bool(entity.remarks and id_query in entity.remarks.upper())
                relation_note_hit = any(
                    relation.note and id_query in relation.note.upper() for relation in entity.relations
                )

                if relation_hit:
                    score = 70.0
                    matched_via = "Relation"
                    matched_field = "relations.target_id"
                    matched_value = id_query
                elif remarks_hit:
                    score = 70.0
                    matched_via = "Remarks"
                    matched_field = "remarks"
                    matched_value = entity.remarks or ""
                elif relation_note_hit:
                    score = 70.0
                    matched_via = "Relation"
                    matched_field = "relations.note"
                    matched_value = next(
                        (relation.note for relation in entity.relations if relation.note and id_query in relation.note.upper()),
                        "",
                    )

            if score <= 0:
                continue

            id_results.append(
                SearchResult(
                    **entity.model_dump(),
                    search_score=score,
                    matched_via=matched_via,
                    match_type=matched_via,
                    matched_field=matched_field,
                    matched_value=matched_value,
                    collision_warning=_build_collision_warning(entity),
                    is_recent=_is_recent(entity),
                )
            )

        id_results.sort(key=lambda item: item.search_score, reverse=True)
        return id_results

    results: list[SearchResult] = []
    for entity in entities:
        score_result = _score_entity(entity, q)
        if score_result.score < MIN_SCORE:
            continue
        results.append(
            SearchResult(
                **entity.model_dump(),
                search_score=round(score_result.score, 2),
                matched_via=score_result.matched_via,
                match_type=score_result.match_type,
                matched_field=score_result.matched_field,
                matched_value=score_result.matched_value,
                collision_warning=_build_collision_warning(entity),
                is_recent=_is_recent(entity),
            )
        )

    results.sort(key=lambda item: item.search_score, reverse=True)
    return results
