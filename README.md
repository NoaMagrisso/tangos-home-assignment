# Tangos — Fullstack Take-Home: Sanctions Entity Explorer

This take-home is designed to take **2 hours**.

## Context

Tangos is an AI-powered compliance investigation platform. Investigators routinely screen organizations against sanctions and watchlist datasets (SDN/OFAC, UK HMT, EU consolidated list) and explore the network of relationships around any flagged entity. This exercise is a small, self-contained slice of that workflow.

## What you'll build

A small fullstack app — **Sanctions Entity Explorer** — that lets a compliance investigator:

1. **Search** for an organization, person, or vessel by name against a provided dataset, and see ranked candidate matches.
2. **Visualize** the chosen entity's **graph of relations** — directly connected entities and the relationship types (e.g., `operates`, `officer_of`, `sibling`, `trade_partner`).

The dataset (`data/sdn_sample.json`) is a small fixture (~32 entries) mimicking the structure of public sanctions lists, augmented with a `relations` array per entity. Treat it as your source of truth — load it on backend startup; do not modify it.

## Starter scaffold

Both `backend/` and `frontend/` ship with a runnable hello-world (FastAPI + `/api/health` endpoint; Vite + React 19 + TypeScript strict). See each folder's `README.md` for run commands. Build on top — replace anything that doesn't fit.

## Requirements

### Backend (Python 3.14+, FastAPI)

A read-only REST API over the fixture. It must support:

- Searching for entities by name (considering both `name` and `aliases`), returning ranked candidates with a match score. The query won't always be an exact match — investigators type partial names and variant spellings. Surface plausible candidates and rank them sensibly.
- Returning the relations graph for a given entity — nodes and edges suitable for direct rendering on the frontend.

### Frontend (React + TypeScript)

Two views:

1. **Search view** — text input (debounced, ~300ms), results table showing entity name, type, primary country, programs, and the match score. Each row is clickable and navigates to the graph view.
2. **Graph view** — a **non-interactive** graph visualization of the selected entity's relations. *Non-interactive* means a static rendering — no need to handle clicks on nodes, drags, or zoom. The selected entity is the central node; directly connected entities are rendered as neighboring nodes; edges are labeled with the relation type.

### What we explicitly do *not* grade

- Pixel-perfect design — usable is enough.
- Auth / users — single-user assumption is fine.
- Accessibility, responsive layouts, or mobile — desktop is enough.
- Performance optimization — clear correctness beats clever memoization.

## Use AI assistants

We expect you to use AI coding assistants (Cursor, Claude Code, GitHub Copilot, ChatGPT, etc.) — that's how Tangos engineers work day to day. Free options exist for all of them if you don't have a paid plan. **No API key is needed for this exercise** (the product itself doesn't call an LLM).

What we want to see in your AI usage:

- **Reviewed and owned code.** Don't accept AI output blindly. We'll spot it.
- **Reasonable commit history** — a series of small, reviewable commits beats one giant "AI dump."

## Deliverables

A git repository (zip is fine if you'd rather not push to GitHub) containing:

```
.
├── backend/                  # your FastAPI app
├── frontend/                 # your React + TS app
├── data/sdn_sample.json      # provided — do not modify
└── README.md                 # this file (or your own — feel free to overwrite, but keep run instructions)
```

Your top-level `README.md` (or `backend/README.md` + `frontend/README.md`) must include:

- Required versions (Python, Node).
- Exact commands to install and run both apps locally.

## Submission

Reply to the email this was sent from with:

- A link to a GitHub/GitLab repo, **or** a zip of the repo with the `.git` folder included (so we can see history).
- Approximate hours spent.

Good luck.
