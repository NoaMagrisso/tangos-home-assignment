# README by Noa - Search Engine Logic

This document summarizes the backend search logic that was implemented for the sanctions explorer, including scoring priorities, guardrails, and tested behavior.

## Search Flow Overview

1. Normalize query text (`normalize_text`): lowercase, remove special characters, collapse spaces.
2. Detect special query mode:
   - If the query is an entity ID (`SDN-xxxxx`) -> run dedicated ID search flow.
   - Otherwise -> run the global multi-field search flow.
3. Score every entity.
4. Keep only results above minimum score threshold.
5. Sort results by score descending.

## Dedicated ID Query Mode

When query matches the ID pattern (`SDN-xxxxx`), the engine uses strict ID rules:

- Exact `entity.id` match -> `100%` score (`matched_via: ID`).
- Entity related by `relations.target_id` -> `70%` score (`matched_via: Relation`).
- ID mentioned in `remarks` or in `relations.note` -> `70%` score.
- No unrelated fuzzy matches are returned in this mode.

This keeps ID queries deterministic and clean.

## Global Multi-Field Search Mode

When query is not an ID query, the engine evaluates multiple fields and selects the best match per entity.

### Field Weights Matrix

| Field | Match Type | Weight |
|---|---|---|
| System ID | Exact | 100% |
| ID Numbers | Exact / Passport | 90% |
| Name / Alias | Fuzzy + Density | 100% (Max) |
| Countries / Programs | Categorical | 60% |
| Remarks / Notes | Fuzzy / Contains | 40% |

### 1) Identity fields (Name + Aliases)

- Uses fuzzy + token similarity + order/proximity logic.
- Applies typo tolerance with penalties.
- Applies low-information token protection.
- Applies **Identity Density** multiplier:

`final_identity_score = base_identity_score * sqrt(query_tokens / entity_name_tokens)`

This prevents partial-name queries from incorrectly reaching 100%.

#### Name overlap and typo handling (explicit)

- **Full overlap** (all meaningful name tokens match in order) receives the strongest identity score.
- **Partial overlap** (only part of the name matches, e.g. surname-only or missing significant token) is visible but penalized.
- **Near typo / letter confusion** (for example `Mader` vs `Madar`) is handled by fuzzy token similarity and receives a reduced score, not an automatic failure.
- **Order sensitivity** exists: reversed or non-ordered token sequences are penalized compared with correct order.
- **Low-info token isolation**: tokens like `al`, `the`, `ltd`, `corp` alone cannot drive high confidence.

#### Library used for fuzzy matching

- Fuzzy scoring is implemented with the `rapidfuzz` library.
- Main matching helpers use:
  - `fuzz.ratio` for token-level similarity
  - `fuzz.partial_ratio` for substring/remarks-style fuzzy checks
- This is combined with token coverage, density, and source-weight rules to produce final ranking.

### 2) Secondary fields

- `id_numbers` exact match -> `90`.
- `countries` match -> `60`.
- `programs` match -> `60`.
- `remarks` / `relations.note` contains or fuzzy hit -> `40`.

### 3) Date fields

Date parsing supports:

- `YYYY-MM-DD`
- `DD/MM/YYYY`
- `YYYY-MM`
- `YYYY`

Date scoring checks both `dates_of_birth` and `list_date`:

- `dates_of_birth`: exact day `75`, month+year `65`, year `55`, off-by-one year same day/month `45`.
- `list_date`: exact day `60`, month+year `50`, year `40`, off-by-one year same day/month `35`.

### 4) Result selection

- The engine computes candidate scores from all applicable fields.
- It selects the strongest result with direct/contextual preference rules:
  - Strong direct identity matches are preferred when close to contextual matches.
  - Date matches do not override a strong Name/Alias match.
- Response includes:
  - `search_score`
  - `matched_via`
  - `match_type`
  - `matched_field`
  - `matched_value`
  - plus existing entity metadata.

## Safety / Noise Controls

- Low-info tokens include: `ai`, `al`, `bin`, `ben`, `the`, `ltd`, `corp`.
- These tokens alone do not produce high-confidence scores.
- Contextual signals (remarks/relations) are intentionally weaker than strong identity hits.

## Verified Run Examples

There is a sample folder of tested runs/images: `run_examples`.

Examples covered there include:

- ID query behavior (`SDN-10001`)
- Name matching and collision scenarios (`Al Madar`, `Al-Madar Holdings Ltd`)
- Country/program examples (`RU`)
- Identity density example (`Kowalska`)
- Additional regression captures (`2023`, `Bosphorus`, `PD Logistics`)
