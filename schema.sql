-- ============================================================
-- AI Revenue Manager — Phase 1 MVP Schema
-- PostgreSQL 14+
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- ENUM TYPES
-- ------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('admin', 'hotel_manager');
CREATE TYPE reservation_status AS ENUM ('confirmed', 'cancelled', 'no_show');
CREATE TYPE upload_status AS ENUM ('processing', 'completed', 'failed');
CREATE TYPE demand_class AS ENUM ('low', 'normal', 'high', 'very_high');
CREATE TYPE recommendation_status AS ENUM ('pending', 'approved', 'rejected');
CREATE TYPE report_type AS ENUM ('daily', 'weekly', 'monthly');
CREATE TYPE message_role AS ENUM ('user', 'assistant');

-- ------------------------------------------------------------
-- HOTELS
-- ------------------------------------------------------------
CREATE TABLE hotels (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    timezone        TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    total_rooms     INT NOT NULL CHECK (total_rooms > 0),
    city            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- USERS
-- ------------------------------------------------------------
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID REFERENCES hotels(id) ON DELETE CASCADE, -- NULL for platform admins
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            user_role NOT NULL DEFAULT 'hotel_manager',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_hotel_id ON users(hotel_id);

-- ------------------------------------------------------------
-- ROOM TYPES
-- ------------------------------------------------------------
CREATE TABLE room_types (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    total_units     INT NOT NULL CHECK (total_units > 0),
    base_rate       NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (hotel_id, name)
);

CREATE INDEX idx_room_types_hotel_id ON room_types(hotel_id);

-- ------------------------------------------------------------
-- UPLOAD BATCHES  (tracks every CSV/Excel upload)
-- ------------------------------------------------------------
CREATE TABLE upload_batches (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    uploaded_by     UUID REFERENCES users(id),
    filename        TEXT NOT NULL,
    row_count       INT NOT NULL DEFAULT 0,
    error_count     INT NOT NULL DEFAULT 0,
    column_mapping  JSONB, -- e.g. {"Check-in": "check_in", "Rate": "rate", ...}
    status          upload_status NOT NULL DEFAULT 'processing',
    error_log       JSONB, -- list of {row, error} for user-facing debugging
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_upload_batches_hotel_id ON upload_batches(hotel_id);

-- ------------------------------------------------------------
-- RESERVATIONS  (cleaned, normalized booking data)
-- ------------------------------------------------------------
CREATE TABLE reservations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id            UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    room_type_id        UUID NOT NULL REFERENCES room_types(id),
    upload_batch_id     UUID REFERENCES upload_batches(id),
    booking_id          TEXT NOT NULL,        -- original ID from source file
    check_in            DATE NOT NULL,
    check_out           DATE NOT NULL,
    booking_date        DATE,                 -- date reservation was made (for lead time/pickup)
    rate                NUMERIC(10,2) NOT NULL CHECK (rate >= 0),
    guests              INT,
    channel             TEXT,                 -- Booking.com, Direct, Agoda, etc.
    status              reservation_status NOT NULL DEFAULT 'confirmed',
    source_row_hash     TEXT,                 -- for duplicate detection
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (check_out > check_in)
);

CREATE INDEX idx_reservations_hotel_dates ON reservations(hotel_id, check_in, check_out);
CREATE INDEX idx_reservations_room_type ON reservations(room_type_id);
CREATE INDEX idx_reservations_status ON reservations(status);
CREATE UNIQUE INDEX idx_reservations_dedup ON reservations(hotel_id, source_row_hash)
    WHERE source_row_hash IS NOT NULL;

-- ------------------------------------------------------------
-- DAILY PERFORMANCE  (pre-aggregated — powers dashboard fast)
-- One row per hotel per date, one row per hotel+room_type per date
-- ------------------------------------------------------------
CREATE TABLE daily_performance (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id            UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    room_type_id        UUID REFERENCES room_types(id), -- NULL = whole-hotel rollup row
    date                DATE NOT NULL,
    rooms_sold          INT NOT NULL DEFAULT 0,
    rooms_available     INT NOT NULL DEFAULT 0,
    occupancy_pct       NUMERIC(5,2),
    adr                 NUMERIC(10,2),
    revpar              NUMERIC(10,2),
    revenue             NUMERIC(12,2),
    pickup_7d           INT DEFAULT 0, -- rooms picked up in trailing 7 days for this date
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (hotel_id, room_type_id, date)
);

CREATE INDEX idx_daily_perf_hotel_date ON daily_performance(hotel_id, date);

-- ------------------------------------------------------------
-- FORECASTS
-- ------------------------------------------------------------
CREATE TABLE forecasts (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id                UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    room_type_id            UUID REFERENCES room_types(id), -- NULL = whole-hotel
    date                    DATE NOT NULL,
    forecast_occupancy_pct  NUMERIC(5,2),
    forecast_adr            NUMERIC(10,2),
    forecast_revenue        NUMERIC(12,2),
    demand_class            demand_class,
    confidence              NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
    model_version           TEXT NOT NULL DEFAULT 'rules-v1',
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (hotel_id, room_type_id, date, model_version)
);

CREATE INDEX idx_forecasts_hotel_date ON forecasts(hotel_id, date);

-- ------------------------------------------------------------
-- PRICING RECOMMENDATIONS
-- ------------------------------------------------------------
CREATE TABLE pricing_recommendations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id            UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    room_type_id        UUID NOT NULL REFERENCES room_types(id),
    date                DATE NOT NULL,
    current_rate        NUMERIC(10,2) NOT NULL,
    recommended_rate    NUMERIC(10,2) NOT NULL,
    reason_text         TEXT,
    reason_factors      JSONB, -- {"pickup_pct":24,"forecast_occupancy":91,"historical_adr_range":[9700,10100]}
    confidence          NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
    status              recommendation_status NOT NULL DEFAULT 'pending',
    decided_by          UUID REFERENCES users(id),
    decided_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (hotel_id, room_type_id, date)
);

CREATE INDEX idx_pricing_rec_hotel_date ON pricing_recommendations(hotel_id, date);
CREATE INDEX idx_pricing_rec_status ON pricing_recommendations(status);

-- ------------------------------------------------------------
-- AI COPILOT
-- ------------------------------------------------------------
CREATE TABLE ai_conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id),
    title           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai_messages (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id     UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
    role                message_role NOT NULL,
    content             TEXT NOT NULL,
    tool_calls          JSONB, -- structured record of which queries the copilot ran
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_messages_conversation ON ai_messages(conversation_id);

-- ------------------------------------------------------------
-- REPORTS
-- ------------------------------------------------------------
CREATE TABLE reports (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hotel_id        UUID NOT NULL REFERENCES hotels(id) ON DELETE CASCADE,
    type            report_type NOT NULL,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    file_url        TEXT,
    generated_by    UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reports_hotel_id ON reports(hotel_id);

-- ------------------------------------------------------------
-- updated_at trigger for hotels
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_hotels_updated_at
    BEFORE UPDATE ON hotels
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
