# Backend — Sanctions Entity Explorer

FastAPI on Python 3.14+. Ships with a `/api/health` endpoint — build the rest on top.

## Setup

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
cd backend
uv sync
```

Or with pip:

```bash
cd backend
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
# or, with the venv activated:
uvicorn app.main:app --reload --port 8000
```

API at http://localhost:8000. OpenAPI UI at http://localhost:8000/docs.

## Notes

- The fixture lives at `../data/sdn_sample.json`. Treat it as read-only — load it once on startup.
- CORS is preconfigured for `http://localhost:5173` (Vite default). Adjust if you change ports.
