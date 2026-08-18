# Phase 1 — API Endpoints (FastAPI)

Auth: JWT bearer token. Every non-admin endpoint is scoped to the caller's `hotel_id` (enforced server-side, never trust a client-supplied hotel_id).

## Auth
| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Email + password → JWT |
| POST | `/auth/refresh` | Refresh token |

## Hotels (admin)
| Method | Path | Description |
|---|---|---|
| POST | `/admin/hotels` | Create hotel |
| GET | `/admin/hotels` | List all hotels |
| POST | `/admin/hotels/{hotel_id}/users` | Create hotel_manager user |

## Hotel Setup
| Method | Path | Description |
|---|---|---|
| GET | `/hotels/me` | Current hotel's profile |
| PATCH | `/hotels/me` | Update hotel name/timezone/currency |
| POST | `/room-types` | Create room type |
| GET | `/room-types` | List room types |
| PATCH | `/room-types/{id}` | Update base rate / total units |

## Data Upload
| Method | Path | Description |
|---|---|---|
| POST | `/uploads` | Upload CSV/XLSX (multipart), returns `upload_batch_id` and detected columns |
| POST | `/uploads/{batch_id}/mapping` | Submit column → schema field mapping |
| POST | `/uploads/{batch_id}/confirm` | Trigger validation + ingestion (async job) |
| GET | `/uploads/{batch_id}` | Poll batch status, row_count, error_count, error_log |
| GET | `/uploads` | List past upload batches |

## Dashboard / Analytics
| Method | Path | Description |
|---|---|---|
| GET | `/analytics/today` | Today's occupancy, ADR, RevPAR, revenue |
| GET | `/analytics/daily?from=&to=` | Daily performance series for a date range |
| GET | `/analytics/summary?period=30d\|60d\|90d` | Rollup KPIs for dashboard cards |

## Forecast
| Method | Path | Description |
|---|---|---|
| GET | `/forecasts?from=&to=&room_type_id=` | Forecast series for a date range |
| POST | `/forecasts/recompute` | Manually trigger recompute (also runs nightly via Celery) |

## Pricing Recommendations
| Method | Path | Description |
|---|---|---|
| GET | `/pricing-recommendations?status=pending` | List recommendations |
| GET | `/pricing-recommendations/{id}` | Single recommendation detail (incl. reason_factors) |
| POST | `/pricing-recommendations/{id}/approve` | Approve → marks decided_by/decided_at |
| POST | `/pricing-recommendations/{id}/reject` | Reject |
| POST | `/pricing-recommendations/what-if` | Body: `{room_type_id, date, new_rate}` → simulated scenario |

## AI Copilot
| Method | Path | Description |
|---|---|---|
| POST | `/ai/conversations` | Start a new conversation |
| POST | `/ai/conversations/{id}/messages` | Send a message; copilot runs structured tool-calls against the hotel's own data, returns answer + `tool_calls` used |
| GET | `/ai/conversations/{id}` | Fetch conversation history |
| GET | `/ai/conversations` | List past conversations |

## Reports
| Method | Path | Description |
|---|---|---|
| POST | `/reports` | Generate a report (`type`, `period_start`, `period_end`) — async job |
| GET | `/reports` | List generated reports |
| GET | `/reports/{id}` | Get report metadata + download URL |

---

### Notes on the AI Copilot endpoint

The copilot should **not** free-generate answers from raw table dumps. It should call a small fixed set of internal tool functions (e.g. `get_occupancy_trend`, `get_top_pickup_dates`, `get_pacing_vs_last_year`, `explain_recommendation(id)`), each backed by a deterministic SQL query, and compose its answer only from those results. This keeps every answer traceable — `ai_messages.tool_calls` stores exactly what was queried, so a hotel manager (or you, debugging a wrong answer) can always see what data the answer was based on.

### Notes on background jobs (Celery)

- `process_upload_batch(batch_id)` — validation, cleaning, dedup, writes to `reservations`
- `recompute_daily_performance(hotel_id, date_range)` — rebuilds `daily_performance` after any data change
- `generate_forecasts(hotel_id)` — runs nightly, populates `forecasts` for next 90 days
- `generate_pricing_recommendations(hotel_id)` — runs after forecasts, populates `pricing_recommendations`
- `generate_report(report_id)` — builds PDF/export, uploads to storage, sets `file_url`
