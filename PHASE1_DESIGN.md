# AI Revenue Manager — Phase 1 Design (Build-Ready)

## 1. Scope
CSV/Excel upload → cleaned data → dashboard → rule-based demand forecast → explainable pricing recommendations → AI copilot (structured, tool-calling only) → basic reports. No PMS/OTA integration, no auto-publish. Two roles: `admin`, `hotel_manager`.

## 2. Files in this package
- `schema.sql` — run directly against PostgreSQL 14+ to create all Phase 1 tables
- `models.py` — SQLAlchemy 2.0 models matching the schema, drop into a FastAPI project
- `forecasting_engine.py` — rule-based forecast, pricing recommendation, and what-if simulator logic (pure Python, no external ML dependency)
- `api_endpoints.md` — full REST API surface for the FastAPI backend

## 3. Why rules-based, not ML, for Phase 1
Most Phase 1 hotels will upload 6–18 months of history. That's not enough data to train a model like XGBoost without overfitting, and a black-box model conflicts with the core "explainable recommendation" requirement. `forecasting_engine.py` instead blends: current booking pace, historical same-weekday baseline, and 7-day pickup momentum — all human-auditable. Every forecast row is stamped with `model_version = "rules-v1"`, so an ML model can be introduced later (Phase 2+) and validated against these rules before replacing them, rather than swapped in blind.

## 4. Data flow
```
CSV/XLSX upload
   → column mapping (user maps their columns to schema fields — not a rigid template)
   → validation + cleaning (dates, dedup, currency, cancellations)
   → reservations table
   → recompute_daily_performance (Celery)
   → generate_forecasts (Celery, nightly)
   → generate_pricing_recommendations (Celery, after forecasts)
   → dashboard / forecast / recommendations screens read from pre-aggregated tables
```
Nothing on the dashboard should ever be computed live from raw `reservations` — always from `daily_performance`, `forecasts`, `pricing_recommendations`. This is what keeps the product fast as data grows.

## 5. Screens (8, matching original spec)
1. Login
2. Hotel Setup (name, rooms, room types, currency, timezone, city)
3. Data Upload (drag-drop + column mapping step, not a fixed template)
4. Dashboard (today's KPIs, 30-day forecast graph, top pricing opportunities)
5. Forecast (calendar/chart view, 30/60/90-day)
6. Pricing Recommendations (current vs recommended, reason, confidence, approve/reject)
7. AI Copilot (chat)
8. Reports (daily/weekly/monthly)

## 6. Guardrails built into the pricing engine (important for trust)
- Max ±30%/-20% single-step rate change (configurable) — the engine can never suggest a wild jump
- Every recommendation ships with `reason_factors` (structured JSON) + `reason_text` (human sentence) — no bare numbers
- What-if simulator results always carry a `confidence_note` — the UI should render this visibly, not bury it, so hotels don't over-trust a single point estimate
- AI Copilot answers only via a fixed set of internal tool functions against the hotel's own structured data — never free-form generation over raw data, which keeps every answer traceable via `ai_messages.tool_calls`

## 7. Suggested build order (roughly 8-12 weeks for a small team)
1. **Week 1-2:** Auth, hotel setup, schema deployed, room types CRUD
2. **Week 3-4:** Upload + column mapping + validation/cleaning pipeline
3. **Week 4-5:** `daily_performance` aggregation job + Dashboard screen
4. **Week 5-7:** Forecasting engine wired to real data + Forecast screen
5. **Week 7-8:** Pricing recommendation engine + Recommendations screen (approve/reject)
6. **Week 8-10:** AI Copilot (tool-calling against the 4-5 core query functions)
7. **Week 10-11:** What-if simulator + Reports
8. **Week 11-12:** Polish, error states, pilot onboarding with 2-3 real hotels

## 8. What "make it live" requires beyond this package
- Hosting: a Postgres instance (RDS/Supabase/Railway all work fine at this scale), a FastAPI deployment (Render/Fly.io/ECS), Redis for Celery
- Object storage (S3 or equivalent) for uploaded files and generated reports
- An LLM provider with function/tool calling for the copilot
- Basic monitoring — at minimum, alerting on failed upload batches and failed forecast jobs, since silent failures here directly cause "bad forecast → bad pricing" per the original design principle

## 9. Explicitly deferred to later phases
PMS/OTA integrations, competitor rate intelligence, automated rate publishing, multi-property/portfolio views, events/market-data feeds. The schema's `hotel_id`-scoped design and `model_version`-stamped forecasts are structured so these can be added without a schema rewrite.
