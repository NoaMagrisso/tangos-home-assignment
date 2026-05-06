from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re

from rapidfuzz import fuzz

from app.models import Entity

LOW_INFO_TOKENS = {"ai", "al", "bin", "ben", "the", "ltd", "corp"}
IMO_PATTERN = re.compile(r"\bIMO\s*(\d{7})\b", re.IGNORECASE)
DIRECT_SOURCE_TYPES = {"primary_name", "alias"}
RELATIONAL_SOURCE_TYPES = {"linked_entity", "relational", "remarks", "country", "program"}
REVERSED_SEQUENCE_PENALTY = 0.7
PROXIMITY_BOOST = 1.4
SIGNIFICANT_TOKEN_FUZZY_MATCH_THRESHOLD = 0.85
SOFT_SIGNIFICANT_TOKEN_THRESHOLD = 0.78
MISSING_PRIMARY_IDENTIFIER_MULTIPLIER = 0.4
COUNTRY_NORMALIZATION_MAP = {
    "US": "USA",
    "USA": "USA",
    "UNITED_STATES": "USA",
    "UK": "UNITED KINGDOM",
    "GB": "UNITED KINGDOM",
    "UNITED_KINGDOM": "UNITED KINGDOM",
}


@dataclass(frozen=True)
class SearchTerm:
    value: str
    match_type: str
    penalty: float


@dataclass(frozen=True)
class ScoreBreakdown:
    base_score: float
    coverage_multiplier: float
    final_score: float


@dataclass(frozen=True)
class EntityScoreResult:
    score: float
    matched_via: str
    match_type: str
    matched_field: str
    matched_value: str


@dataclass(frozen=True)
class ParsedDateQuery:
    year: int
    month: int | None = None
    day: int | None = None


def normalize_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def extract_imo_terms(remarks: str | None) -> list[str]:
    if not remarks:
        return []
    return [f"IMO {imo_number}" for imo_number in IMO_PATTERN.findall(remarks)]


def build_search_terms(
    entity: Entity,
    entity_name_by_id: dict[str, str],
    alias_penalty: float,
    metadata_penalty: float,
) -> list[SearchTerm]:
    linked_names = [
        entity_name_by_id[relation.target_id]
        for relation in entity.relations
        if relation.target_id in entity_name_by_id
    ]

    terms: list[SearchTerm] = [
        SearchTerm(value=entity.name, match_type="primary_name", penalty=1.0),
        *[
            SearchTerm(value=alias, match_type="alias", penalty=alias_penalty)
            for alias in entity.aliases
        ],
        *[
            SearchTerm(value=imo_term, match_type="imo", penalty=alias_penalty)
            for imo_term in extract_imo_terms(entity.remarks)
        ],
        *[
            SearchTerm(value=linked_name, match_type="linked_entity", penalty=alias_penalty)
            for linked_name in linked_names
        ],
        *[
            SearchTerm(value=country_code, match_type="country", penalty=metadata_penalty)
            for country_code in entity.countries
        ],
        *[
            SearchTerm(value=program_name, match_type="program", penalty=metadata_penalty)
            for program_name in entity.programs
        ],
    ]

    if entity.remarks:
        terms.append(
            SearchTerm(value=entity.remarks, match_type="remarks", penalty=metadata_penalty)
        )

    return terms


def _has_adjacent_query_tokens(query_tokens: list[str], candidate_tokens: list[str]) -> bool:
    if len(query_tokens) < 2:
        return False

    for start_index in range(len(candidate_tokens) - len(query_tokens) + 1):
        if candidate_tokens[start_index : start_index + len(query_tokens)] == query_tokens:
            return True
    return False


def _best_token_similarity(query_token: str, candidate_tokens: list[str]) -> float:
    if not candidate_tokens:
        return 0.0
    # Low-information tokens should only match as standalone whole words.
    if query_token in LOW_INFO_TOKENS:
        return 1.0 if query_token in candidate_tokens else 0.0
    return max(fuzz.ratio(query_token, candidate_token) / 100 for candidate_token in candidate_tokens)


def _tokens_in_query_order(query_tokens: list[str], candidate_tokens: list[str]) -> bool:
    position = -1
    for query_token in query_tokens:
        try:
            position = candidate_tokens.index(query_token, position + 1)
        except ValueError:
            return False
    return True


def _source_multiplier(match_type: str) -> float:
    if match_type in DIRECT_SOURCE_TYPES:
        return 1.0
    if match_type in RELATIONAL_SOURCE_TYPES:
        return 0.7
    return 1.0


def _identity_density_multiplier(query: str, entity_name: str) -> float:
    query_tokens = len(normalize_text(query).split())
    entity_tokens = len(normalize_text(entity_name).split())
    if query_tokens <= 0 or entity_tokens <= 0:
        return 1.0
    density_multiplier = (query_tokens / entity_tokens) ** 0.5
    density_multiplier = min(1.0, density_multiplier)
    print(
        f"[DEBUG] Query: {query} | Entity: {entity_name} | Density Multiplier: {density_multiplier}"
    )
    return density_multiplier


def normalize_country(value: str) -> str:
    normalized = normalize_text(value).replace(" ", "_").upper()
    return COUNTRY_NORMALIZATION_MAP.get(normalized, normalized)


def _parse_date_query(value: str) -> ParsedDateQuery | None:
    raw_value = value.strip()
    if not raw_value:
        return None

    # YYYY-MM-DD
    try:
        parsed = date.fromisoformat(raw_value)
        return ParsedDateQuery(year=parsed.year, month=parsed.month, day=parsed.day)
    except ValueError:
        pass

    # DD/MM/YYYY
    try:
        parsed = datetime.strptime(raw_value, "%d/%m/%Y").date()
        return ParsedDateQuery(year=parsed.year, month=parsed.month, day=parsed.day)
    except ValueError:
        pass

    # YYYY-MM
    if re.fullmatch(r"\d{4}-\d{2}", raw_value):
        year_text, month_text = raw_value.split("-")
        year = int(year_text)
        month = int(month_text)
        if 1 <= month <= 12:
            return ParsedDateQuery(year=year, month=month)
        return None

    # YYYY
    if re.fullmatch(r"\d{4}", raw_value):
        return ParsedDateQuery(year=int(raw_value))

    return None


def _collect_query_countries(query_tokens: list[str], normalized_query: str) -> set[str]:
    countries: set[str] = set()
    for token in query_tokens:
        country = normalize_country(token)
        if country in COUNTRY_NORMALIZATION_MAP.values() or len(country) in {2, 3}:
            countries.add(country)
    if normalized_query:
        countries.add(normalize_country(normalized_query))
    return countries


def _date_candidate_score(parsed_query: ParsedDateQuery, candidate: date, *, is_list_date: bool) -> float:
    if parsed_query.day is not None and parsed_query.month is not None:
        if (
            candidate.year == parsed_query.year
            and candidate.month == parsed_query.month
            and candidate.day == parsed_query.day
        ):
            return 60.0 if is_list_date else 75.0
        if (
            candidate.month == parsed_query.month
            and candidate.day == parsed_query.day
            and abs(candidate.year - parsed_query.year) == 1
        ):
            return 35.0 if is_list_date else 45.0
        return 0.0

    if parsed_query.month is not None:
        if candidate.year == parsed_query.year and candidate.month == parsed_query.month:
            return 50.0 if is_list_date else 65.0
        return 0.0

    if candidate.year == parsed_query.year:
        return 40.0 if is_list_date else 55.0

    return 0.0


def _score_date_match(query: str, dates_of_birth: list[date], list_date: date) -> tuple[float, str, str] | None:
    parsed_query = _parse_date_query(query)
    if not parsed_query:
        return None

    best_score = 0.0
    best_field = ""
    best_value = ""

    for dob in dates_of_birth:
        score = _date_candidate_score(parsed_query, dob, is_list_date=False)
        if score > best_score:
            best_score = score
            best_field = "dates_of_birth"
            best_value = dob.isoformat()

    list_date_score = _date_candidate_score(parsed_query, list_date, is_list_date=True)
    if list_date_score > best_score:
        best_score = list_date_score
        best_field = "list_date"
        best_value = list_date.isoformat()

    if best_score > 0:
        return best_score, best_field, best_value
    return None


def identity_identifier_multiplier(query: str, entity: Entity) -> float:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return 1.0

    significant_tokens = [
        token for token in dict.fromkeys(normalized_query.split()) if token not in LOW_INFO_TOKENS
    ]
    if not significant_tokens:
        return 1.0

    identity_tokens = normalize_text(" ".join([entity.name, *entity.aliases])).split()
    missing_identifiers = [
        token
        for token in significant_tokens
        if _best_token_similarity(token, identity_tokens) < SIGNIFICANT_TOKEN_FUZZY_MATCH_THRESHOLD
    ]
    if missing_identifiers:
        return MISSING_PRIMARY_IDENTIFIER_MULTIPLIER
    return 1.0


def score_term(
    query: str, candidate: str, penalty: float, match_type: str, entity_name: str
) -> ScoreBreakdown:
    normalized_query = normalize_text(query)
    normalized_candidate = normalize_text(candidate)
    if not normalized_query or not normalized_candidate:
        return ScoreBreakdown(base_score=0.0, coverage_multiplier=0.0, final_score=0.0)

    query_tokens = list(dict.fromkeys(normalized_query.split()))
    candidate_tokens = normalized_candidate.split()
    non_stop_query_tokens = [token for token in query_tokens if token not in LOW_INFO_TOKENS]

    if not query_tokens:
        return ScoreBreakdown(base_score=0.0, coverage_multiplier=0.0, final_score=0.0)

    token_similarities = [
        _best_token_similarity(query_token, candidate_tokens) for query_token in query_tokens
    ]
    base_similarity = sum(token_similarities) / len(token_similarities)
    if match_type in RELATIONAL_SOURCE_TYPES:
        base_similarity = min(base_similarity, 0.9)

    matched_tokens = {token for token in query_tokens if token in candidate_tokens}
    matched_count = len(matched_tokens)

    score = base_similarity * penalty * _source_multiplier(match_type)
    base_score = score

    # Primary identifier penalty: keep visible but significantly lower.
    missing_non_stop = []
    strongest_non_stop_similarity = 0.0
    for token in non_stop_query_tokens:
        similarity = _best_token_similarity(token, candidate_tokens)
        strongest_non_stop_similarity = max(strongest_non_stop_similarity, similarity)
        if similarity < SIGNIFICANT_TOKEN_FUZZY_MATCH_THRESHOLD:
            missing_non_stop.append(token)
    coverage_multiplier = 1.0
    if missing_non_stop:
        # Keep typo-close identity matches visible and competitive.
        if strongest_non_stop_similarity >= SOFT_SIGNIFICANT_TOKEN_THRESHOLD:
            coverage_multiplier = 0.75
        else:
            coverage_multiplier = MISSING_PRIMARY_IDENTIFIER_MULTIPLIER
        score *= coverage_multiplier

    # Low-information-only queries/matches should stay low-confidence.
    significant_fuzzy_matches = [
        _best_token_similarity(query_token, candidate_tokens)
        for query_token in non_stop_query_tokens
    ]
    has_significant_fuzzy_match = any(
        similarity >= SIGNIFICANT_TOKEN_FUZZY_MATCH_THRESHOLD
        for similarity in significant_fuzzy_matches
    )
    only_low_info_exact_match = (
        set(query_tokens).issubset(LOW_INFO_TOKENS)
        or (matched_tokens and matched_tokens.issubset(LOW_INFO_TOKENS))
    )
    if only_low_info_exact_match and not has_significant_fuzzy_match:
        score = min(score, 0.15)

    has_full_sequence = _tokens_in_query_order(query_tokens, candidate_tokens)
    # Penalize reversed/non-ordered token layouts when all tokens exist.
    if matched_count == len(query_tokens) and not has_full_sequence:
        score *= REVERSED_SEQUENCE_PENALTY

    # Adjacent query token sequence indicates stronger confidence.
    if matched_count > 1 and _has_adjacent_query_tokens(query_tokens, candidate_tokens):
        score *= PROXIMITY_BOOST

    all_tokens_present = matched_count == len(query_tokens)
    high_similarity_all_tokens = all(
        _best_token_similarity(query_token, candidate_tokens) >= 0.9 for query_token in query_tokens
    )

    final_score = min(score, 1.0)
    if final_score >= 1.0 and not (all_tokens_present and high_similarity_all_tokens):
        final_score = 0.99

    return ScoreBreakdown(
        base_score=round(base_score * 100, 2),
        coverage_multiplier=round(coverage_multiplier, 2),
        final_score=round(final_score * 100, 2),
    )


def score_entity_fields(
    *,
    query: str,
    query_tokens: list[str],
    entity: Entity,
    search_terms: list[SearchTerm],
) -> EntityScoreResult:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return EntityScoreResult(0.0, "none", "unknown", "none", "")

    # Highest-priority hard match: entity ID exact match bypasses all other logic.
    if normalize_text(entity.id) == normalized_query:
        return EntityScoreResult(
            score=100.0,
            matched_via="ID",
            match_type="ID",
            matched_field="id",
            matched_value=entity.id,
        )

    matches: list[EntityScoreResult] = []
    is_low_info_only_query = bool(query_tokens) and all(token in LOW_INFO_TOKENS for token in query_tokens)

    # Identity logic for name and aliases with mandatory density penalty.
    density_multiplier = _identity_density_multiplier(query, entity.name)
    identity_terms = [
        ("Name", "name", entity.name, 1.0),
        *[("Alias", "aliases", alias, 0.9) for alias in entity.aliases],
    ]
    for match_type, matched_field, candidate, penalty in identity_terms:
        breakdown = score_term(query, candidate, penalty, matched_field, entity.name)
        identity_score = breakdown.final_score * density_multiplier
        if is_low_info_only_query:
            identity_score = min(identity_score, 15.0)
        matches.append(
            EntityScoreResult(
                score=round(identity_score, 2),
                matched_via=match_type,
                match_type=match_type,
                matched_field=matched_field,
                matched_value=candidate,
            )
        )

    # Secondary identifiers list: exact match at 90%.
    for id_number in entity.id_numbers:
        if normalize_text(id_number) == normalized_query:
            matches.append(
                EntityScoreResult(
                    score=90.0,
                    matched_via="Identifier",
                    match_type="Identifier",
                    matched_field="id_numbers",
                    matched_value=id_number,
                )
            )

    # Countries and programs: weighted base score of 60%.
    normalized_entity_countries = {normalize_country(country) for country in entity.countries}
    country_hits = _collect_query_countries(query_tokens, query) & normalized_entity_countries
    if country_hits:
        matches.append(
            EntityScoreResult(
                score=60.0,
                matched_via="Country",
                match_type="Country",
                matched_field="countries",
                matched_value=sorted(country_hits)[0],
            )
        )

    normalized_query_upper = normalized_query.upper()
    for program in entity.programs:
        program_norm = normalize_text(program).upper()
        if normalized_query_upper == program_norm:
            matches.append(
                EntityScoreResult(
                    score=60.0,
                    matched_via="Program",
                    match_type="Program",
                    matched_field="programs",
                    matched_value=program,
                )
            )
            break

    # Remarks and relation notes: weighted base score of 40% via contains/fuzzy.
    relation_notes = [relation.note for relation in entity.relations if relation.note]
    textual_sources = [("remarks", entity.remarks or ""), *[("relations.note", note) for note in relation_notes]]
    for field_name, text_value in textual_sources:
        normalized_text_value = normalize_text(text_value)
        if not normalized_text_value:
            continue
        contains_hit = normalized_query in normalized_text_value
        fuzzy_hit = fuzz.partial_ratio(normalized_query, normalized_text_value) >= 75
        if contains_hit or fuzzy_hit:
            matches.append(
                EntityScoreResult(
                    score=40.0,
                    matched_via="Remarks" if field_name == "remarks" else "Relation",
                    match_type="Remarks" if field_name == "remarks" else "Relation",
                    matched_field=field_name,
                    matched_value=text_value,
                )
            )

    # Date handling kept as low-priority supplemental search signal.
    date_match = _score_date_match(query, entity.dates_of_birth, entity.list_date)
    if date_match:
        matches.append(
            EntityScoreResult(
                score=date_match[0],
                matched_via="Date",
                match_type="Date",
                matched_field=date_match[1],
                matched_value=date_match[2],
            )
        )

    direct_match_types = {"Name", "Alias", "ID", "Identifier"}
    contextual_match_types = {"Program", "Country", "Remarks", "Relation", "Date"}

    best_direct = max(
        (match for match in matches if match.match_type in direct_match_types),
        key=lambda match: match.score,
        default=None,
    )
    best_contextual = max(
        (match for match in matches if match.match_type in contextual_match_types),
        key=lambda match: match.score,
        default=None,
    )

    if best_direct and best_contextual:
        if best_contextual.match_type == "Date" and best_direct.score >= 80:
            return best_direct
        # Prefer identity signals when reasonably close to contextual evidence.
        if best_direct.score >= best_contextual.score * 0.75:
            return best_direct
        return best_contextual

    if best_direct:
        return best_direct
    if best_contextual:
        return best_contextual
    return EntityScoreResult(0.0, "none", "unknown", "none", "")
