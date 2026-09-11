# NagrikAI Backend (FastAPI)

FastAPI backend for the NagrikAI citizen complaint-triage system. Classifies complaints via Google Gemini API, routes them to the correct municipal department, tracks SLAs, and flags breaches.

## Stack

- **Python 3.10+**
- **FastAPI** — REST API framework
- **SQLite** (`tickets.db`) — embedded database, zero setup
- **Google Gemini (AI Studio)** — AI extraction, classification, and response generation (free tier available)
- **Pydantic v2** — request/response validation
- **Uvicorn** — ASGI server

## Folder Structure

```
backend/
  main.py              # FastAPI app, CORS, route definitions
  ai_engine.py         # Gemini API: extraction, clarification, response generation
  database.py          # SQLite setup, insert/get/update ticket, breach check
  constants.py         # DEPARTMENTS dict, ticket schema constants
  models.py            # Pydantic request/response models
  seed_demo_data.py    # Standalone script: inserts demo tickets (1 breached + 4 varied)
  test_complaints.json # 20 synthetic test complaints for manual testing
  run_tests.py         # End-to-end HTTP test script
  requirements.txt
  .env.example         # GOOGLE_API_KEY placeholder
  tickets.db           # Created automatically on first run
```

## Setup

### 1. Create a virtual environment

```bash
cd backend
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Google AI Studio (Gemini) API key

Copy `.env.example` to `.env` and fill in your real API key:

```bash
copy .env.example .env
# then edit .env:
GOOGLE_API_KEY=your_real_key_here
GEMINI_MODEL=gemini-2.0-flash
```

**Get a free API key:**
1. Go to https://aistudio.google.com/apikey
2. Sign in with a Google account
3. Click **Create API key** → select a project → copy the key

**Free tier rate limits (as of 2025):** Gemini flash-tier models have generous free-tier RPM/RPD limits. See the current numbers at:
https://ai.google.dev/gemini-api/docs/rate-limits

If no API key is set (or `google-generativeai` is unavailable), the AI engine will fall back to a safe default (category=Other, urgency=medium, generic clarification question) so endpoints still respond 200 OK. No endpoint will crash.

### 4. (Optional) Seed demo data

Inserts 5 demo tickets (one guaranteed breached, four varied categories/urgencies) so the dashboard isn't empty:

```bash
python seed_demo_data.py
```

It's safe to run multiple times — if tickets already exist, the script skips insertion.

## Run the server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

- **API root (health check):** http://localhost:8000/ → `{"status": "ok"}`
- **Auto-docs (Swagger UI):** http://localhost:8000/docs — test every endpoint interactively here
- **ReDoc:** http://localhost:8000/redoc

## API Contract

| Method | Endpoint | Purpose |
|---|---|---|
| `GET`  | `/` | Health check → `{"status": "ok"}` |
| `POST` | `/api/analyze` | Analyze raw complaint text → ticket JSON (saved to DB only if complete) |
| `POST` | `/api/clarify` | Merge original + citizen reply → updated ticket (saved if complete) |
| `GET`  | `/api/tickets` | All tickets, newest first |
| `GET`  | `/api/tickets/{ticket_id}` | Single ticket by ID |
| `PATCH`| `/api/tickets/{ticket_id}/status` | Update status / breach flag / escalation |
| `POST` | `/api/check-breaches` | Manual trigger: scan all tickets, flag any past deadline as breached |
| `GET`  | `/api/stats` | Dashboard counts: `{by_category, by_department}` |

### Request bodies

```json
// POST /api/analyze
{ "text": "complaint text here" }

// POST /api/clarify
{ "original_text": "original complaint...", "reply": "sector 4 near bus stop" }

// PATCH /api/tickets/{id}/status
{ "status": "in_progress", "breached": false, "escalation_action": null }
```

### Ticket JSON schema

```json
{
  "ticket_id": "TKT-0001",
  "raw_text": "original complaint text",
  "category": "Water Supply",
  "department": "Water Supply Board",
  "urgency": "high",
  "sla_hours": 4,
  "sla_deadline": "2025-01-01T12:00:00",
  "status": "open",
  "breached": false,
  "location": "Sector 4, near bus stop",
  "missing_fields": [],
  "clarification_question": null,
  "citizen_response_message": "Thank you...",
  "created_at": "2025-01-01T12:00:00",
  "escalation_action": null
}
```

## CORS

Enabled globally with `allow_origins=["*"]` for hackathon ease. Your frontend running on `localhost:5173` (Vite) or a Stitch static export can call it directly.

## SLA Reference (`constants.py`)

Each of the 10 categories maps to a department and a 3-tier SLA (hours):

| # | Category | Dept | High | Med | Low |
|---|---|---|---|---|---|
| 1 | Water Supply | Water Supply Board | 4h | 24h | 72h |
| 2 | Electricity | Electricity Dept | 2h | 12h | 48h |
| 3 | Roads & Potholes | PWD | 8h | 48h | 120h |
| 4 | Garbage & Sanitation | Municipal Sanitation | 6h | 24h | 72h |
| 5 | Streetlights | Municipal Lighting | 12h | 48h | 120h |
| 6 | Drainage & Sewage | Drainage & Sewage Board | 4h | 24h | 72h |
| 7 | Public Safety | Local Police Dept | 1h | 6h | 24h |
| 8 | Noise Complaint | Noise Control Cell | 4h | 24h | 72h |
| 9 | Illegal Construction | Town Planning | 24h | 72h | 168h |
| 10 | Other | General Grievance Cell | 12h | 48h | 120h |

Tune these values at the top of `constants.py` — all SLAs flow from one source of truth.

## Testing with `test_complaints.json`

Use the 20 sample complaints in `test_complaints.json` to exercise every code path. Try pasting any of these into the `/api/analyze` box at `/docs`.

- IDs 1-5: simple/clear → tickets save immediately
- ID 6 (`"no water supply for three days"`) → should ask for location
- IDs 11-13: multi-issue → most urgent gets picked
- IDs 14-16: sarcastic → intent should be inferred
- IDs 17-18: repeat/escalation → urgency bumped to high
- IDs 19-20: edge cases (spam/gibberish) → safe fallback + clarification

## Testing (Automated)

`run_tests.py` runs 8 test groups end-to-end against a live backend. It is a standalone script (no pytest required).

1. Start the server:

```bash
cd backend
uvicorn main:app --reload --port 8000
```

2. In a **separate terminal**, run:

```bash
cd backend
python run_tests.py
```

What it checks (all against `http://localhost:8000`):

1. **Health** — `GET /` returns `{"status": "ok"}`. Aborts immediately with a clear message if the server isn't running.
2. **Docs** — `GET /docs` returns 200 (Swagger UI is reachable).
3. **Analyze × 20** — every complaint from `test_complaints.json` posted to `/api/analyze`; schema validated, category checked against the 10 fixed categories, `missing_fields` non-empty ⇒ `clarification_question` set.
4. **Clarify loop** — `"no water supply for three days"` → `/api/analyze` → `/api/clarify` with reply `"Koregaon Park, Pune"`; verifies `missing_fields=[]`, `ticket_id` assigned`, `citizen_response_message` set.
5. **Persistence** — `GET /api/tickets` contains the ticket ID from step 4.
6. **Stats** — `GET /api/stats` returns non-empty `by_category` and `by_department`.
7. **Seed + breach** — runs `seed_demo_data.py`, then confirms at least one `status=breached` ticket with a non-null `escalation_action`, plus `POST /api/check-breaches` returns 200.
8. **CORS** — `GET /api/tickets` with `Origin: http://localhost:5173` confirms `Access-Control-Allow-Origin` response header.

Each line is prefixed ✅ / ❌, and the script prints `X/Y checks passed` plus a one-line failure list at the end. It exits non-zero on any failure (CI-ready).

## Wipe & re-seed

Delete `tickets.db` and re-run `python seed_demo_data.py` for a clean slate.
