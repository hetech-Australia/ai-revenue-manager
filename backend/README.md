# AI Revenue Manager — Phase 1 Backend

A rules-based, explainable hotel revenue-management MVP: CSV/Excel upload →
dashboard → demand forecast → pricing recommendations → AI copilot.

## What's here
```
backend/
  app/
    main.py                      # FastAPI app entrypoint
    models.py                    # SQLAlchemy ORM models (matches schema.sql)
    core/
      config.py                  # DB connection, settings
      security.py                # auth (JWT + password hashing)
    routers/
      auth.py                    # POST /auth/login
      analytics.py               # GET /analytics/today, /daily, /summary
      pricing.py                 # pricing recommendations + what-if simulator
      uploads.py                 # CSV/Excel upload + column mapping
    services/
      forecasting_engine.py      # rule-based forecast + pricing + what-if logic
  requirements.txt
  .env.example
schema.sql                       # run this against Postgres first
```

## For the developer picking this up

1. **Create a Postgres database**, then run:
   ```
   psql "$DATABASE_URL" -f schema.sql
   ```

2. **Set up the backend**:
   ```
   cd backend
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # fill in real values
   uvicorn app.main:app --reload
   ```
   API will be live at `http://localhost:8000`, interactive docs at `/docs`.

3. **What's implemented vs. what's a stub:**
   - ✅ Auth (login, JWT), hotel-scoped access control
   - ✅ Analytics endpoints (dashboard KPIs)
   - ✅ Pricing recommendations (list/approve/reject) + what-if simulator
   - ✅ Upload endpoint (parses CSV/XLSX, returns detected columns)
   - ⚠️ **Upload ingestion (`/uploads/{id}/confirm`) is a stub.** It needs to be
     wired to a Celery background job that: re-fetches the file from object
     storage, applies the saved column mapping, validates/cleans rows (see
     the "Data Processing Engine" requirements — missing dates, duplicates,
     cancellations, currency, date formats), and writes to `reservations`.
   - ⚠️ **`recompute_daily_performance`, `generate_forecasts`,
     `generate_pricing_recommendations` are not yet implemented as jobs.**
     The pure logic for forecasting/pricing already exists in
     `services/forecasting_engine.py` — someone needs to write the Celery
     tasks that pull data from `reservations`/`daily_performance`, call
     that logic, and write results to `forecasts` / `pricing_recommendations`.
   - ⚠️ **AI Copilot router not yet built.** Design: it should call a small
     fixed set of internal query functions (e.g. `get_occupancy_trend`,
     `get_pacing_vs_last_year`) via LLM tool-calling — not free-generate
     from raw data. See PHASE1_DESIGN.md for the reasoning.
   - ⚠️ **Reports endpoint not yet built** (PDF/export generation).
   - ⚠️ **Room type & hotel setup CRUD endpoints not yet built** — needed
     before upload/pricing can be tested end-to-end.
   - ⚠️ **Frontend (Next.js) not started** — this repo is backend-only.

4. **Suggested first milestone for a freelancer**: get hotel setup → room
   types → upload → ingestion job → dashboard working end-to-end with one
   real hotel's data. Forecasting/pricing/copilot can follow once that
   pipeline is solid, since everything downstream depends on clean data
   in `reservations` and `daily_performance`.

See `PHASE1_DESIGN.md` (in the parent design package) for the full product
spec, screen list, and reasoning behind key decisions (rules-based
forecasting instead of ML, explainability requirements, guardrails).
