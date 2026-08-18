"""
Forecasting + Pricing Engine — Phase 1 (rules-based, explainable)

Design decision: Phase 1 hotels will typically upload 6-18 months of
history. That's too little to safely train XGBoost/LightGBM without
overfitting, and a black-box model undermines the "explainable
recommendation" requirement. So Phase 1 ships a deterministic,
rules-based engine. ML (Phase 2+) can be introduced once a hotel has
12+ months of clean data, and should be A/B tested against these
rules before replacing them.

model_version = "rules-v1" is stamped on every forecast row so we can
compare against future ML versions later.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean


# ---------------------------------------------------------------
# 1. DEMAND FORECAST
# ---------------------------------------------------------------

@dataclass
class ForecastInput:
    target_date: date
    rooms_available: int
    rooms_currently_booked: int          # bookings on file today for target_date
    historical_same_weekday_occupancy: list[float]  # e.g. last 8 occurrences of this weekday, as %
    pickup_last_7_days: int              # rooms added to target_date's booking count in last 7 days
    typical_pickup_7_days: float         # average 7-day pickup for this weekday, from history


@dataclass
class ForecastResult:
    forecast_occupancy_pct: float
    demand_class: str
    confidence: float
    factors: dict


def forecast_demand(inp: ForecastInput) -> ForecastResult:
    current_occ_pct = (inp.rooms_currently_booked / inp.rooms_available) * 100

    # Historical baseline for this specific weekday
    hist_baseline = mean(inp.historical_same_weekday_occupancy) if inp.historical_same_weekday_occupancy else current_occ_pct

    # Pickup momentum: how much faster/slower is this date filling vs typical
    if inp.typical_pickup_7_days > 0:
        pickup_index = inp.pickup_last_7_days / inp.typical_pickup_7_days
    else:
        pickup_index = 1.0

    # Blend: current pace (50%), historical weekday baseline (30%), pickup momentum adjustment (20%)
    pace_projection = current_occ_pct + (hist_baseline - current_occ_pct) * 0.3
    momentum_adjustment = (pickup_index - 1.0) * 15  # each 100% above/below typical pace shifts forecast +/-15pts
    forecast_occ = pace_projection + momentum_adjustment
    forecast_occ = max(0, min(100, forecast_occ))

    # Demand classification
    if forecast_occ >= 90:
        demand_class = "very_high"
    elif forecast_occ >= 75:
        demand_class = "high"
    elif forecast_occ >= 50:
        demand_class = "normal"
    else:
        demand_class = "low"

    # Confidence: more historical samples + more current bookings on the books = higher confidence
    n_hist = len(inp.historical_same_weekday_occupancy)
    sample_confidence = min(1.0, n_hist / 8)          # maxes out at 8+ historical weekday samples
    booking_confidence = min(1.0, inp.rooms_currently_booked / max(1, inp.rooms_available * 0.3))
    confidence = round(0.5 * sample_confidence + 0.5 * booking_confidence, 2)

    return ForecastResult(
        forecast_occupancy_pct=round(forecast_occ, 1),
        demand_class=demand_class,
        confidence=confidence,
        factors={
            "current_occupancy_pct": round(current_occ_pct, 1),
            "historical_weekday_baseline_pct": round(hist_baseline, 1),
            "pickup_last_7_days": inp.pickup_last_7_days,
            "typical_pickup_7_days": inp.typical_pickup_7_days,
            "pickup_index": round(pickup_index, 2),
            "historical_samples_used": n_hist,
        },
    )


# ---------------------------------------------------------------
# 2. PRICING RECOMMENDATION
# ---------------------------------------------------------------

@dataclass
class PricingInput:
    current_rate: float
    forecast: ForecastResult
    remaining_inventory: int
    historical_adr_for_similar_demand: list[float]  # ADRs achieved on comparably-strong past dates
    max_increase_pct: float = 0.30   # guardrail: never recommend more than +30% in one step
    max_decrease_pct: float = 0.20   # guardrail: never recommend more than -20% in one step


@dataclass
class PricingRecommendation:
    recommended_rate: float
    reason_text: str
    reason_factors: dict
    confidence: float


DEMAND_MULTIPLIER = {
    "very_high": 1.18,
    "high": 1.08,
    "normal": 1.00,
    "low": 0.90,
}


def recommend_price(inp: PricingInput) -> PricingRecommendation:
    demand_class = inp.forecast.demand_class
    base_multiplier = DEMAND_MULTIPLIER[demand_class]

    # Anchor toward historical ADR achieved under similar demand, if we have it
    if inp.historical_adr_for_similar_demand:
        hist_adr_mid = mean(inp.historical_adr_for_similar_demand)
        # Blend: 60% current-rate-times-multiplier, 40% historical achieved ADR
        target_rate = 0.6 * (inp.current_rate * base_multiplier) + 0.4 * hist_adr_mid
    else:
        target_rate = inp.current_rate * base_multiplier

    # Scarcity nudge: very low remaining inventory pushes rate up further
    if inp.remaining_inventory <= 5 and demand_class in ("high", "very_high"):
        target_rate *= 1.05

    # Apply guardrails so the engine never suggests an extreme jump
    max_rate = inp.current_rate * (1 + inp.max_increase_pct)
    min_rate = inp.current_rate * (1 - inp.max_decrease_pct)
    recommended_rate = max(min_rate, min(max_rate, target_rate))
    recommended_rate = round(recommended_rate / 50) * 50  # round to nearest 50 (currency-appropriate)

    pct_change = ((recommended_rate - inp.current_rate) / inp.current_rate) * 100
    direction = "Increase" if pct_change > 0 else "Decrease" if pct_change < 0 else "Hold"

    hist_range_text = ""
    if inp.historical_adr_for_similar_demand:
        lo, hi = min(inp.historical_adr_for_similar_demand), max(inp.historical_adr_for_similar_demand)
        hist_range_text = f", and historical dates with similar demand achieved ADR of ₹{lo:,.0f}–₹{hi:,.0f}"

    reason_text = (
        f"{direction} rate from ₹{inp.current_rate:,.0f} → ₹{recommended_rate:,.0f}. "
        f"Demand is forecast to reach {inp.forecast.forecast_occupancy_pct:.0f}% occupancy "
        f"({demand_class.replace('_', ' ')} demand). "
        f"Booking pickup is at {inp.forecast.factors['pickup_index']*100:.0f}% of the property's "
        f"typical pace for this date{hist_range_text}."
    )

    return PricingRecommendation(
        recommended_rate=recommended_rate,
        reason_text=reason_text,
        reason_factors={
            "demand_class": demand_class,
            "forecast_occupancy_pct": inp.forecast.forecast_occupancy_pct,
            "pickup_index": inp.forecast.factors["pickup_index"],
            "remaining_inventory": inp.remaining_inventory,
            "historical_adr_range": (
                [min(inp.historical_adr_for_similar_demand), max(inp.historical_adr_for_similar_demand)]
                if inp.historical_adr_for_similar_demand else None
            ),
            "pct_change": round(pct_change, 1),
        },
        confidence=inp.forecast.confidence,
    )


# ---------------------------------------------------------------
# 3. WHAT-IF SIMULATOR
# ---------------------------------------------------------------

# Simple price-elasticity model. This is intentionally conservative and
# should be shown to users with a confidence range, not a single point
# estimate (see design notes). Elasticity coefficient is a starting
# default and should become hotel-specific once enough data exists.
DEFAULT_ELASTICITY = -0.4  # % occupancy change per 1% rate change


def simulate_what_if(current_rate: float, new_rate: float, forecast_occupancy_pct: float,
                      rooms_available: int, elasticity: float = DEFAULT_ELASTICITY) -> dict:
    pct_rate_change = (new_rate - current_rate) / current_rate
    pct_occ_change = pct_rate_change * elasticity
    scenario_occ = max(0, min(100, forecast_occupancy_pct * (1 + pct_occ_change)))

    current_revenue = (forecast_occupancy_pct / 100) * rooms_available * current_rate
    scenario_revenue = (scenario_occ / 100) * rooms_available * new_rate
    revenue_impact_pct = ((scenario_revenue - current_revenue) / current_revenue) * 100 if current_revenue else 0

    return {
        "current": {
            "rate": current_rate,
            "occupancy_pct": round(forecast_occupancy_pct, 1),
            "revenue": round(current_revenue, 2),
        },
        "scenario": {
            "rate": new_rate,
            "occupancy_pct": round(scenario_occ, 1),
            "revenue": round(scenario_revenue, 2),
        },
        "estimated_revenue_impact_pct": round(revenue_impact_pct, 1),
        "confidence_note": (
            "Estimate based on a simplified elasticity model. Treat as a directional "
            "guide, not a guarantee — accuracy improves as more of the hotel's own "
            "price-change history becomes available."
        ),
    }
