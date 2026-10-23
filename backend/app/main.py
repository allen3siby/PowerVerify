import io
import csv
import math
from datetime import datetime, timedelta
from typing import Optional, List
import numpy as np

from fastapi import FastAPI, HTTPException, Query, Depends, status, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse

from .database import (
    init_db,
    record_decision,
    get_observation_status_map,
    get_all_observation_statuses,
    get_anomaly_case_map,
    get_decision_history,
    get_all_decisions,
    get_accounts,
    get_account_by_id,
    get_account_by_meter_id,
    save_account,
    get_verification_run_by_id,
    get_verification_history_for_account,
    create_case,
    get_cases,
    get_case_by_id,
    update_case_status,
    update_case_assignment,
    record_case_decision,
    add_case_note,
    get_case_notes,
    get_case_audit_trail,
    get_all_tariffs,
    get_active_tariff,
    create_or_update_tariff,
    get_synthetic_bills,
    get_synthetic_bill_by_id,
    get_synthetic_payments,
    get_billing_verification_history,
    get_payment_reconciliation_history,
    get_billing_summary_metrics,
    seed_billing_and_payments_if_empty,
    get_active_model_config,
    get_active_model_run,
    get_latest_successful_model_run,
    get_model_runs_history,
    get_model_run_by_id,
    compare_model_runs,
)
from .data_pipeline import run_pipeline, state, init_pipeline_from_saved_config, is_pipeline_running
from .verification_engine import run_account_verification
from .billing_engine import verify_synthetic_bill, reconcile_bill_payments
from .security import get_current_user, require_role, UserContext
from .schemas import (
    DatasetSummaryResponse,
    DashboardStatsResponse,
    DashboardChartResponse,
    ChartDataPoint,
    MeterListItem,
    MeterHistoryResponse,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewQueueResponse,
    ReviewQueueItem,
    SettingsReanalyzeRequest,
    ActiveConfigSchema,
    ModelRunSummarySchema,
    ModelComparisonSchema,
    ModelRerunRequest,
    ModelConfigDetailResponse,
    ModelRerunResponse,
    AccountSchema,
    VerificationRunResponse,
    VerificationRunRequest,
    CaseSchema,
    CaseListResponse,
    CaseDetailResponse,
    CaseStatusUpdateRequest,
    CaseAssignmentRequest,
    CaseDecisionRequest,
    CaseNoteRequest,
    CaseNoteSchema,
    CaseAuditEventSchema,
    TariffRuleSchema,
    TariffRuleUpdateRequest,
    SyntheticBillSchema,
    SyntheticBillListResponse,
    SyntheticPaymentSchema,
    BillingVerificationResultSchema,
    PaymentReconciliationResultSchema,
    BillingSummaryResponse,
)

from contextlib import asynccontextmanager

def sync_initial_cases():
    """
    Initializes cases table from existing review decisions and top flagged anomalies if empty.
    Preserves all existing decisions without duplicates.
    """
    existing_cases = get_cases(page=1, page_size=1)
    if existing_cases["total"] > 0:
        return

    # 1. Sync from existing review decisions
    decisions = get_all_decisions()
    for d in decisions:
        obs_id = d["observation_id"]
        meter_id = d["meter_id"]
        account = get_account_by_meter_id(meter_id)
        account_id = account["account_id"] if account else f"ACCT-{meter_id}"
        consumer_id = account["consumer_id"] if account else f"CONS-{meter_id}"

        source_id = f"ANOM_{obs_id}"
        case_dict, is_new = create_case(
            source_finding_id=source_id,
            account_id=account_id,
            consumer_id=consumer_id,
            meter_id=meter_id,
            title=f"Consumption Review Case — Meter {meter_id} ({d['date']})",
            description=f"Recorded review decision: {d['decision']}. Observation {obs_id}.",
            finding_category="CONSUMPTION_SURGE",
            severity="MEDIUM",
            priority="MEDIUM",
            actor_id="system",
            actor_role="ADMIN",
        )
        if is_new:
            record_case_decision(
                case_id=case_dict["case_id"],
                decision=d["decision"],
                decision_reason=d.get("notes") or "Preserved from prior review decision log.",
                actor_id="officer.sharma",
                actor_role="VERIFICATION_OFFICER",
                notes=d.get("notes"),
            )

    # 2. Populate cases for the top 30 flagged anomalies to ensure rich immediate case queue
    df, _, _ = run_pipeline()
    anoms = df[df["is_anomaly"]].sort_values(by="anomaly_severity", ascending=False).head(30)
    for _, row in anoms.iterrows():
        obs_id = row["observation_id"]
        source_id = f"ANOM_{obs_id}"
        meter_id = row["meter_id"]
        account = get_account_by_meter_id(meter_id)
        account_id = account["account_id"] if account else f"ACCT-{meter_id}"
        consumer_id = account["consumer_id"] if account else f"CONS-{meter_id}"

        cat = "CONSUMPTION_SURGE" if row["anomaly_direction"] == "high" else "CONSUMPTION_DROP"
        sev = "CRITICAL" if row["anomaly_severity"] >= 0.98 else ("HIGH" if row["anomaly_severity"] >= 0.9 else "MEDIUM")
        pri = "URGENT" if sev == "CRITICAL" else ("HIGH" if sev == "HIGH" else "MEDIUM")

        create_case(
            source_finding_id=source_id,
            account_id=account_id,
            consumer_id=consumer_id,
            meter_id=meter_id,
            title=f"Flagged {row['anomaly_direction'].upper()} Usage Anomaly — Meter {meter_id} ({row['date']})",
            description=row["reason"],
            finding_category=cat,
            severity=sev,
            priority=pri,
            actor_id="system",
            actor_role="ADMIN",
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Trigger initial data load and Isolation Forest execution from saved SQLite config
    init_pipeline_from_saved_config()
    sync_initial_cases()
    yield

app = FastAPI(
    title="PowerVerify API",
    description="Smart-Meter Electricity Consumption Anomaly Detection and Verification System",
    version="1.0.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [
    "https://powerverify.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https://powerverify(-[a-z0-9\-]+)?\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Sanitize validation error messages to ensure non-JSON-compliant floats (NaN, Inf)
    are converted to strings instead of crashing Starlette's JSONResponse serializer.
    """
    clean_errors = []
    for err in exc.errors():
        err_copy = dict(err)
        if "input" in err_copy:
            val = err_copy["input"]
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                err_copy["input"] = str(val)
        clean_errors.append(err_copy)
    return JSONResponse(status_code=422, content={"detail": clean_errors})

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "PowerVerify",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data_loaded": state.df_analyzed is not None,
    }

@app.get("/api/dataset/summary", response_model=DatasetSummaryResponse)
def get_dataset_summary():
    df, summary, _ = run_pipeline()
    return DatasetSummaryResponse(**summary)

@app.get("/api/dashboard/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats():
    df, summary, model_meta = run_pipeline()
    status_details = get_all_observation_statuses()
    case_map = get_anomaly_case_map()

    # Identify flagged anomalies (unique reviewable observations)
    flagged_df = df[df["isolation_forest_anomaly"]].copy()
    flagged_total = len(flagged_df)
    flagged_meters = int(flagged_df["meter_id"].nunique())

    # Calculate review counts
    flagged_ids = set(flagged_df["observation_id"])
    resolved_count = 0
    for obs_id in flagged_ids:
        st = status_details.get(obs_id, {})
        if st.get("review_status") == "REVIEWED":
            resolved_count += 1
    
    pending_count = flagged_total - resolved_count
    open_field_visits = sum(1 for st in case_map.values() if st not in ("RESOLVED", "CLOSED"))
    resolved_cases = sum(1 for st in case_map.values() if st in ("RESOLVED", "CLOSED"))

    return DashboardStatsResponse(
        total_meters=summary["total_meters"],
        total_readings=summary["valid_readings"],
        flagged_anomalies=flagged_total,
        flagged_meters=flagged_meters,
        pending_reviews=pending_count,
        resolved_reviews=resolved_count,
        high_anomalies=model_meta["high_usage_anomalies"],
        low_anomalies=model_meta["low_usage_anomalies"],
        pattern_anomalies=model_meta["pattern_anomalies"],
        start_date=summary["start_date"],
        end_date=summary["end_date"],
        model_name=model_meta["model_name"],
        contamination=model_meta["contamination"],
        statistical_anomalies=model_meta.get("statistical_anomalies", 0),
        isolation_forest_anomalies=model_meta.get("isolation_forest_anomalies", 0),
        open_field_visits=open_field_visits,
        resolved_cases=resolved_cases,
        active_run_id=model_meta.get("run_id"),
    )

@app.get("/api/dashboard/chart", response_model=DashboardChartResponse)
def get_dashboard_chart(
    time_range: str = Query("all", pattern="^(all|30d|90d|1y)$"),
    meter_id: Optional[str] = None
):
    df, _, _ = run_pipeline()
    status_details = get_all_observation_statuses()
    case_map = get_anomaly_case_map()

    chart_df = df.copy()
    if meter_id:
        chart_df = chart_df[chart_df["meter_id"] == meter_id]
        if chart_df.empty:
            raise HTTPException(status_code=404, detail=f"Meter {meter_id} not found")

    # Time range filtering
    if time_range != "all":
        max_date = chart_df["date_parsed"].max()
        days_map = {"30d": 30, "90d": 90, "1y": 365}
        cutoff = max_date - timedelta(days=days_map[time_range])
        chart_df = chart_df[chart_df["date_parsed"] >= cutoff]

    # For aggregate overview without a specific meter, aggregate daily across meters
    if not meter_id:
        # 1. Compute daily system mean across all available historical dates to prevent window clipping
        daily_full = df.groupby(["date", "date_parsed"]).agg(
            kwh=("kwh", "mean"),
            high_anoms=("is_anomaly", lambda s: ((s == True) & (df.loc[s.index, "anomaly_direction"] == "high")).sum()),
            low_anoms=("is_anomaly", lambda s: ((s == True) & (df.loc[s.index, "anomaly_direction"] == "low")).sum()),
            pattern_anoms=("is_anomaly", lambda s: ((s == True) & (df.loc[s.index, "anomaly_direction"] == "pattern")).sum()),
            total_anoms=("is_anomaly", "sum"),
            avg_severity=("anomaly_severity", "mean"),
        ).reset_index().sort_values("date_parsed")

        # 2. Compute mathematically valid trailing 30-day median and MAD on the system series
        roll = daily_full["kwh"].rolling(window=30, min_periods=5)
        overall_med = float(daily_full["kwh"].median())
        overall_mad = float(np.median(np.abs(daily_full["kwh"] - overall_med))) or 0.5

        daily_full["trailing_median"] = roll.median().fillna(overall_med)
        calc_mad = lambda w: float(np.median(np.abs(w - np.median(w))))
        daily_full["trailing_mad"] = roll.apply(calc_mad, raw=True).fillna(overall_mad)
        daily_full["trailing_mad"] = np.maximum(daily_full["trailing_mad"], 0.05)

        scale = 1.4826 * daily_full["trailing_mad"]
        daily_full["expected_upper"] = np.round(daily_full["trailing_median"] + 2.5 * scale, 2)
        daily_full["expected_lower"] = np.round(np.maximum(0.0, daily_full["trailing_median"] - 2.5 * scale), 2)

        # 3. Filter by time_range
        if time_range != "all":
            max_date = daily_full["date_parsed"].max()
            days_map = {"30d": 30, "90d": 90, "1y": 365}
            cutoff = max_date - timedelta(days=days_map[time_range])
            daily_chart = daily_full[daily_full["date_parsed"] >= cutoff].copy()
        else:
            daily_chart = daily_full.copy()

        points = []
        for _, row in daily_chart.iterrows():
            kwh_val = float(round(row["kwh"], 2))
            upper_val = float(round(row["expected_upper"], 2))
            lower_val = float(round(row["expected_lower"], 2))
            high_m = int(row["high_anoms"])
            low_m = int(row["low_anoms"])
            tot_m = int(row["total_anoms"])

            # System-level aggregate anomaly criteria
            is_high = kwh_val > upper_val
            is_low = kwh_val < lower_val
            is_anom = is_high or is_low

            if is_high:
                direction = "high"
                reason = (
                    f"System High Usage Anomaly: Grid-wide mean consumption ({kwh_val:.2f} kWh) "
                    f"exceeded historical upper threshold ({upper_val:.2f} kWh) by +{kwh_val - upper_val:.2f} kWh. "
                    f"{tot_m} individual meter-level anomalies on this date ({high_m} high, {low_m} low)."
                )
            elif is_low:
                direction = "low"
                reason = (
                    f"System Low Usage Anomaly: Grid-wide mean consumption ({kwh_val:.2f} kWh) "
                    f"dropped below historical lower threshold ({lower_val:.2f} kWh, -{lower_val - kwh_val:.2f} kWh). "
                    f"{tot_m} individual meter-level anomalies on this date ({high_m} high, {low_m} low)."
                )
            else:
                direction = "normal"
                if tot_m > 0:
                    reason = (
                        f"System mean ({kwh_val:.2f} kWh) is within expected range ({lower_val:.2f} – {upper_val:.2f} kWh). "
                        f"{tot_m} individual meter anomalies recorded ({high_m} high, {low_m} low) — select specific meters above or check Review Queue."
                    )
                else:
                    reason = f"System-wide daily mean: {kwh_val:.2f} kWh across all active meters (expected range: {lower_val:.2f} – {upper_val:.2f} kWh)."

            points.append(ChartDataPoint(
                date=row["date"],
                meter_id=None,
                kwh=kwh_val,
                observed_consumption=kwh_val,
                trailing_median=float(round(row["trailing_median"], 2)),
                expected_lower=lower_val,
                expected_upper=upper_val,
                is_anomaly=is_anom,
                statistical_anomaly=is_anom,
                isolation_forest_anomaly=False,
                anomaly_direction=direction,
                anomaly_severity=float(round(row["avg_severity"], 3)),
                anomaly_score=float(round(row["avg_severity"], 3)),
                detection_method="STATISTICAL_MAD" if is_anom else "NORMAL",
                reason=reason,
                anomaly_reasons=reason,
                review_decision="N/A",
                review_status="N/A (Aggregated System)",
                case_status=None,
            ))
    else:
        # Individual meter time series
        points = []
        for _, row in chart_df.iterrows():
            obs_id = row["observation_id"]
            st_info = status_details.get(obs_id, {})
            is_anom = bool(row["is_anomaly"])
            current_status = st_info.get("current_status", "Pending Review" if is_anom else "Normal")
            rev_status = current_status
            rev_decision = st_info.get("review_decision", "PENDING" if is_anom else "NORMAL")
            case_st = case_map.get(obs_id)
            kwh_val = float(round(row["kwh"], 2))

            points.append(ChartDataPoint(
                date=row["date"],
                meter_id=row["meter_id"],
                kwh=kwh_val,
                observed_consumption=kwh_val,
                trailing_median=float(round(row["trailing_median"], 2)),
                expected_lower=float(round(row["expected_lower"], 2)),
                expected_upper=float(round(row["expected_upper"], 2)),
                is_anomaly=is_anom,
                statistical_anomaly=bool(row["statistical_anomaly"]),
                isolation_forest_anomaly=bool(row["isolation_forest_anomaly"]),
                anomaly_direction=row["anomaly_direction"],
                anomaly_severity=float(round(row["anomaly_severity"], 3)),
                anomaly_score=float(round(row.get("anomaly_score", row["anomaly_severity"]), 4)),
                detection_method=row.get("detection_method", "STATISTICAL_MAD"),
                reason=row["reason"],
                anomaly_reasons=row["reason"],
                review_decision=rev_decision,
                review_status=rev_status,
                case_status=case_st,
            ))

    return DashboardChartResponse(
        points=points,
        total_points=len(points),
        sample_rate=1,
        start_date=points[0].date if points else "",
        end_date=points[-1].date if points else "",
    )

@app.get("/api/meters", response_model=List[MeterListItem])
def get_meters():
    df, _, _ = run_pipeline()
    status_map = get_observation_status_map()

    meters = []
    for meter_id, group in df.groupby("meter_id", sort=True):
        anomalies = group[group["is_anomaly"]]
        anom_count = len(anomalies)
        
        pending_count = 0
        for obs_id in anomalies["observation_id"]:
            if status_map.get(obs_id, "Pending Review") == "Pending Review":
                pending_count += 1

        meters.append(MeterListItem(
            meter_id=meter_id,
            district=group["district"].iloc[0],
            total_days=len(group),
            mean_kwh=float(round(group["kwh"].mean(), 2)),
            max_kwh=float(round(group["kwh"].max(), 2)),
            anomaly_count=anom_count,
            high_anomaly_count=int((anomalies["anomaly_direction"] == "high").sum()),
            low_anomaly_count=int((anomalies["anomaly_direction"] == "low").sum()),
            pending_review_count=pending_count,
        ))

    return meters

@app.get("/api/meters/{meter_id}/history", response_model=MeterHistoryResponse)
def get_meter_history(
    meter_id: str,
    time_range: str = Query("all", pattern="^(all|30d|90d|1y)$")
):
    df, _, _ = run_pipeline()
    status_details = get_all_observation_statuses()
    case_map = get_anomaly_case_map()

    meter_df = df[df["meter_id"] == meter_id].copy()
    if meter_df.empty:
        raise HTTPException(status_code=404, detail=f"Meter '{meter_id}' not found in CEEW dataset.")

    if time_range != "all":
        max_date = meter_df["date_parsed"].max()
        days_map = {"30d": 30, "90d": 90, "1y": 365}
        cutoff = max_date - timedelta(days=days_map[time_range])
        meter_df = meter_df[meter_df["date_parsed"] >= cutoff]

    points = []
    for _, row in meter_df.iterrows():
        obs_id = row["observation_id"]
        st_info = status_details.get(obs_id, {})
        is_anom = bool(row["is_anomaly"])
        current_status = st_info.get("current_status", "Pending Review" if is_anom else "Normal")
        rev_status = current_status
        rev_decision = st_info.get("review_decision", "PENDING" if is_anom else "NORMAL")
        case_st = case_map.get(obs_id)
        kwh_val = float(round(row["kwh"], 2))

        points.append(ChartDataPoint(
            date=row["date"],
            meter_id=meter_id,
            kwh=kwh_val,
            observed_consumption=kwh_val,
            trailing_median=float(round(row["trailing_median"], 2)),
            expected_lower=float(round(row["expected_lower"], 2)),
            expected_upper=float(round(row["expected_upper"], 2)),
            is_anomaly=is_anom,
            statistical_anomaly=bool(row["statistical_anomaly"]),
            isolation_forest_anomaly=bool(row["isolation_forest_anomaly"]),
            anomaly_direction=row["anomaly_direction"],
            anomaly_severity=float(round(row["anomaly_severity"], 3)),
            anomaly_score=float(round(row.get("anomaly_score", row["anomaly_severity"]), 4)),
            detection_method=row.get("detection_method", "STATISTICAL_MAD"),
            reason=row["reason"],
            anomaly_reasons=row["reason"],
            review_decision=rev_decision,
            review_status=rev_status,
            case_status=case_st,
        ))

    return MeterHistoryResponse(
        meter_id=meter_id,
        district=meter_df["district"].iloc[0],
        total_readings=len(meter_df),
        mean_kwh=float(round(meter_df["kwh"].mean(), 2)),
        median_kwh=float(round(meter_df["kwh"].median(), 2)),
        anomaly_count=int(meter_df["is_anomaly"].sum()),
        points=points,
    )

@app.get("/api/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(
    meter_id: Optional[str] = None,
    direction: Optional[str] = Query(None, pattern="^(all|high|low|pattern)$"),
    status: Optional[str] = Query(None),
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    df, _, _ = run_pipeline()
    status_details = get_all_observation_statuses()
    case_map = get_anomaly_case_map()

    # Filter to anomalies only
    anom_df = df[df["isolation_forest_anomaly"]].copy()

    # Map review status and current decision
    anom_df["current_status"] = anom_df["observation_id"].map(
        lambda x: status_details.get(x, {}).get("current_status", "Pending Review")
    )
    anom_df["review_status"] = anom_df["current_status"]
    anom_df["review_decision"] = anom_df["observation_id"].map(
        lambda x: status_details.get(x, {}).get("review_decision", "PENDING")
    )

    if meter_id:
        anom_df = anom_df[anom_df["meter_id"] == meter_id]

    if direction and direction != "all":
        anom_df = anom_df[anom_df["anomaly_direction"] == direction]

    if status and status != "all":
        st_lower = status.lower()
        if st_lower == "pending" or status == "Pending Review":
            anom_df = anom_df[anom_df["current_status"] == "Pending Review"]
        elif st_lower == "reviewed":
            anom_df = anom_df[anom_df["current_status"] != "Pending Review"]
        else:
            anom_df = anom_df[anom_df["current_status"] == status]

    if search:
        s = search.lower().strip()
        anom_df = anom_df[
            anom_df["observation_id"].str.lower().str.contains(s) |
            anom_df["meter_id"].str.lower().str.contains(s) |
            anom_df["date"].str.contains(s) |
            anom_df["reason"].str.lower().str.contains(s)
        ]

    # Sort descending by date
    anom_df.sort_values(by="date_parsed", ascending=False, inplace=True)
    total_count = len(anom_df)
    total_pages = max(1, (total_count + page_size - 1) // page_size)

    # Paginate
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_df = anom_df.iloc[start_idx:end_idx]

    items = []
    for _, row in page_df.iterrows():
        obs_id = row["observation_id"]
        kwh_val = float(round(row["kwh"], 2))
        items.append(ReviewQueueItem(
            observation_id=obs_id,
            meter_id=row["meter_id"],
            district=row["district"],
            date=row["date"],
            kwh=kwh_val,
            observed_consumption=kwh_val,
            trailing_median=float(round(row["trailing_median"], 2)),
            expected_lower=float(round(row["expected_lower"], 2)),
            expected_upper=float(round(row["expected_upper"], 2)),
            is_anomaly=True,
            statistical_anomaly=bool(row["statistical_anomaly"]),
            isolation_forest_anomaly=bool(row["isolation_forest_anomaly"]),
            anomaly_direction=row["anomaly_direction"],
            anomaly_severity=float(round(row["anomaly_severity"], 3)),
            anomaly_score=float(round(row.get("anomaly_score", row["anomaly_severity"]), 4)),
            detection_method=row.get("detection_method", "STATISTICAL_MAD"),
            reason=row["reason"],
            anomaly_reasons=row["reason"],
            review_decision=row["review_decision"],
            review_status=row["review_status"],
            case_status=case_map.get(obs_id),
            updated_at=status_details.get(obs_id, {}).get("updated_at"),
        ))

    return ReviewQueueResponse(
        items=items,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

@app.post("/api/reviews", response_model=ReviewDecisionResponse)
def submit_review(req: ReviewDecisionRequest):
    allowed_decisions = {
        "Acknowledge / No Further Action",
        "Mark for Field Visit",
        "High Usage Authorized",
    }
    if req.decision not in allowed_decisions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision '{req.decision}'. Allowed: {list(allowed_decisions)}"
        )

    df, _, _ = run_pipeline()
    obs_match = df[df["observation_id"] == req.observation_id]
    if obs_match.empty:
        raise HTTPException(status_code=404, detail=f"Observation '{req.observation_id}' not found.")

    row = obs_match.iloc[0]
    result = record_decision(
        observation_id=req.observation_id,
        meter_id=row["meter_id"],
        date=row["date"],
        kwh=float(row["kwh"]),
        anomaly_direction=row["anomaly_direction"],
        decision=req.decision,
        notes=req.notes,
    )

    return ReviewDecisionResponse(
        success=True,
        observation_id=result["observation_id"],
        meter_id=result["meter_id"],
        date=result["date"],
        previous_status=result["previous_status"],
        new_status=result["new_status"],
        notes=result["notes"],
        timestamp=result["timestamp"],
    )

@app.get("/api/reviews/{observation_id}/history")
def get_reviews_history(observation_id: str):
    return get_decision_history(observation_id)

@app.get("/api/model/config", response_model=ModelConfigDetailResponse)
def get_model_configuration():
    saved = get_active_model_config()
    active_run = get_active_model_run()
    prev_run = get_latest_successful_model_run(exclude_run_id=active_run["run_id"] if active_run else None)
    running = is_pipeline_running()
    active_cfg = {
        "contamination": state.contamination,
        "n_estimators": state.n_estimators,
        "random_state": state.random_state,
        "active_run_id": state.active_run_id or (active_run["run_id"] if active_run else None),
        "updated_at": saved.get("updated_at")
    }
    return ModelConfigDetailResponse(
        saved_configuration=ActiveConfigSchema(**saved),
        active_configuration=ActiveConfigSchema(**active_cfg),
        current_run=ModelRunSummarySchema(**active_run) if active_run else None,
        previous_run=ModelRunSummarySchema(**prev_run) if prev_run else None,
        is_running=running,
        model_metadata=state.model_metadata
    )

@app.post("/api/model/rerun", response_model=ModelRerunResponse)
def rerun_isolation_forest(req: ModelRerunRequest):
    if is_pipeline_running():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A model rerun is currently already in progress. Please wait for completion."
        )

    prev_run = get_active_model_run()
    try:
        df, summary, model_meta = run_pipeline(
            contamination=req.contamination,
            n_estimators=req.n_estimators,
            random_state=req.random_state,
            force_reload=True
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(re))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model execution failed: {str(e)}")

    curr_run = get_active_model_run()
    comparison = None
    if prev_run and curr_run and prev_run["run_id"] != curr_run["run_id"]:
        try:
            comp_dict = compare_model_runs(curr_run["run_id"], prev_run["run_id"])
            comparison = ModelComparisonSchema(**comp_dict)
        except Exception:
            comparison = None

    return ModelRerunResponse(
        success=True,
        message=f"Isolation Forest recomputed successfully with contamination={req.contamination:.3f} and {req.n_estimators} trees.",
        run=ModelRunSummarySchema(**curr_run),
        comparison=comparison,
        model_metadata=model_meta
    )

@app.post("/api/settings/reanalyze")
def reanalyze_model(req: SettingsReanalyzeRequest):
    if is_pipeline_running():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A model rerun is currently already in progress. Please wait for completion."
        )
    prev_run = get_active_model_run()
    try:
        df, summary, model_meta = run_pipeline(
            contamination=req.contamination,
            n_estimators=req.n_estimators,
            random_state=getattr(req, "random_state", 42),
            force_reload=True
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(re))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model execution failed: {str(e)}")

    curr_run = get_active_model_run()
    comparison = None
    if prev_run and curr_run and prev_run["run_id"] != curr_run["run_id"]:
        try:
            comp_dict = compare_model_runs(curr_run["run_id"], prev_run["run_id"])
            comparison = comp_dict
        except Exception:
            comparison = None

    return {
        "success": True,
        "message": f"Isolation Forest recomputed with contamination={req.contamination} and n_estimators={req.n_estimators}.",
        "model_metadata": model_meta,
        "run": curr_run,
        "comparison": comparison,
    }

@app.get("/api/model/runs", response_model=List[ModelRunSummarySchema])
def get_model_runs(limit: int = Query(20, ge=1, le=100)):
    runs = get_model_runs_history(limit=limit)
    return [ModelRunSummarySchema(**r) for r in runs]

@app.get("/api/model/runs/{run_id}", response_model=ModelRunSummarySchema)
def get_model_run(run_id: str):
    run = get_model_run_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Model run {run_id} not found.")
    return ModelRunSummarySchema(**run)

@app.get("/api/model/compare", response_model=ModelComparisonSchema)
def compare_runs(
    current_run_id: Optional[str] = Query(None),
    previous_run_id: Optional[str] = Query(None)
):
    if not current_run_id:
        act = get_active_model_run()
        if not act:
            raise HTTPException(status_code=404, detail="No active model run found.")
        current_run_id = act["run_id"]
    if not previous_run_id:
        prev = get_latest_successful_model_run(exclude_run_id=current_run_id)
        if not prev:
            raise HTTPException(status_code=404, detail="No previous model run found to compare with.")
        previous_run_id = prev["run_id"]
    try:
        res = compare_model_runs(current_run_id, previous_run_id)
        return ModelComparisonSchema(**res)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/export/csv")
def export_csv(flagged_only: bool = Query(True)):
    df, _, _ = run_pipeline()
    status_map = get_observation_status_map()

    export_df = df[df["is_anomaly"]].copy() if flagged_only else df.copy()
    export_df["review_status"] = export_df["observation_id"].map(lambda x: status_map.get(x, "Pending Review" if flagged_only else "Normal"))

    output = io.StringIO()
    cols = [
        "observation_id", "meter_id", "district", "date", "kwh",
        "trailing_median", "expected_lower", "expected_upper",
        "anomaly_direction", "anomaly_severity", "reason", "review_status"
    ]
    export_df[cols].to_csv(output, index=False)
    output.seek(0)

    filename = "powerverify_flagged_anomalies.csv" if flagged_only else "powerverify_all_observations.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/export/reviews/csv")
def export_reviews_csv():
    decisions = get_all_decisions()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "observation_id", "meter_id", "date", "decision", "notes",
        "previous_status", "new_status", "created_at"
    ])
    writer.writeheader()
    for d in decisions:
        writer.writerow(d)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=powerverify_review_decisions.csv"}
    )

@app.get("/api/export/report")
def export_report():
    df, summary, model_meta = run_pipeline()
    status_map = get_observation_status_map()
    decisions = get_all_decisions()

    report_lines = [
        "# PowerVerify: Smart-Meter Consumption Anomaly Analysis Report",
        f"Generated At: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## 1. Verified Source Dataset",
        f"- Dataset Name: {summary['dataset_name']}",
        f"- Authoring Institution: {summary['source_institution']}",
        f"- Districts Covered: {', '.join(summary['districts'])} (Uttar Pradesh, India)",
        f"- Total Meters Monitored: {summary['total_meters']}",
        f"- Observation Period: {summary['start_date']} to {summary['end_date']}",
        f"- Total Valid Daily Observations: {summary['valid_readings']:,}",
        f"- Sampling Interval: {summary['sampling_interval']}",
        f"- Unit of Measurement: {summary['measurement_unit']}",
        f"- Mean Consumption: {summary['mean_kwh']:.2f} kWh/day",
        f"- Median Consumption: {summary['median_kwh']:.2f} kWh/day",
        f"- Peak Observation: {summary['max_kwh']:.2f} kWh/day",
        "",
        "## 2. Machine Learning Model Methodology",
        f"- Algorithm: {model_meta['model_name']}",
        f"- Algorithm Family: {model_meta['algorithm_family']}",
        f"- Contamination Setting: {model_meta['contamination']}",
        f"- Estimators: {model_meta['n_estimators']} isolation trees",
        f"- Random State: {model_meta['random_state']}",
        f"- Features: {', '.join(model_meta['features_used'])}",
        "- Historical Expected Range: Trailing 30-day Median ± 2.5 * (1.4826 * MAD)",
        "",
        "## 3. Anomaly Detection Findings",
        f"- Total Flagged Observations: {model_meta['total_anomalies']} ({model_meta['anomaly_percentage']}% of records)",
        f"- High-Usage Anomalies: {model_meta['high_usage_anomalies']} (exceeding expected upper boundary)",
        f"- Low-Usage Anomalies: {model_meta['low_usage_anomalies']} (below expected lower boundary or extreme drop)",
        f"- Pattern / Volatility Anomalies: {model_meta['pattern_anomalies']} (unusual day-over-day delta)",
        "",
        "## 4. Investigation & Review Status",
        f"- Total Decision Records Logged: {len(decisions)}",
        "- Action Categories Supported:",
        "  1. Acknowledge / No Further Action",
        "  2. Mark for Field Visit",
        "  3. High Usage Authorized",
        "",
        "## 5. Critical Engineering & Ethical Clarification",
        "- Unsupervised anomaly detection isolates statistical outliers relative to historical consumption baselines.",
        "- Flagged anomalies DO NOT constitute proof of electricity theft, tampering, or fraud.",
        "- Low-usage readings may indicate household vacancies, supply outages, or meter telemetry errors.",
        "- High-usage readings may reflect authorized temporary equipment or seasonal heat waves.",
        "- Human-in-the-loop verification is mandatory before taking field or administrative action."
    ]

    return PlainTextResponse(
        "\n".join(report_lines),
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=powerverify_analysis_report.md"}
    )

# =============================================================
# Consumer Account Endpoints
# =============================================================

@app.get("/api/accounts", response_model=List[AccountSchema])
def list_accounts(
    search: Optional[str] = None,
    district: Optional[str] = Query(None, pattern="^(all|Bareilly|Mathura)$")
):
    return get_accounts(search=search, district=district)

@app.get("/api/accounts/{account_id}", response_model=AccountSchema)
def get_account_detail(account_id: str):
    acct = get_account_by_id(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")
    return acct

# =============================================================
# Account Verification Engine Endpoints
# =============================================================

@app.post("/api/verification/run", response_model=VerificationRunResponse)
def execute_verification(
    req: VerificationRunRequest,
    user: UserContext = Depends(require_role(["ADMIN", "VERIFICATION_OFFICER"]))
):
    try:
        result = run_account_verification(
            account_id=req.account_id,
            scope=req.scope or "FULL_HISTORICAL_AUDIT",
            time_window_days=req.time_window_days,
            actor_id=user.user_id,
            actor_role=user.role,
            auto_create_cases=req.auto_create_cases if req.auto_create_cases is not None else True,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Verification execution error: {str(e)}")

@app.get("/api/verification/{verification_id}", response_model=VerificationRunResponse)
def get_verification_details(verification_id: str):
    run = get_verification_run_by_id(verification_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Verification run '{verification_id}' not found.")
    return run

@app.get("/api/accounts/{account_id}/verification-history", response_model=List[VerificationRunResponse])
def get_account_verification_history(account_id: str, limit: int = Query(20, ge=1, le=100)):
    history = get_verification_history_for_account(account_id, limit=limit)
    expanded = []
    for h in history:
        full_run = get_verification_run_by_id(h["verification_id"])
        if full_run:
            expanded.append(full_run)
    return expanded

# =============================================================
# Verification Case Management & Audit Trail Endpoints
# =============================================================

@app.get("/api/cases", response_model=CaseListResponse)
def list_cases(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    assignee: Optional[str] = None,
    meter_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    return get_cases(
        status=status,
        priority=priority,
        category=category,
        assignee=assignee,
        meter_id=meter_id,
        search=search,
        page=page,
        page_size=page_size,
    )

@app.get("/api/cases/{case_id}", response_model=CaseDetailResponse)
def get_case_detail(case_id: str):
    c = get_case_by_id(case_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    account = get_account_by_id(c["account_id"])
    notes = get_case_notes(case_id)
    audit_trail = get_case_audit_trail(case_id)

    # Fetch recent telemetry points for meter
    recent_history = None
    if c.get("meter_id"):
        try:
            chart_res = get_dashboard_chart(time_range="90d", meter_id=c["meter_id"])
            recent_history = chart_res.points
        except Exception:
            recent_history = []

    return CaseDetailResponse(
        case=CaseSchema(**c),
        account=AccountSchema(**account) if account else None,
        notes=[CaseNoteSchema(**n) for n in notes],
        audit_events=[CaseAuditEventSchema(**a) for a in audit_trail],
        recent_meter_history=recent_history,
    )

@app.post("/api/cases/{case_id}/status", response_model=CaseSchema)
def change_case_status(
    case_id: str,
    req: CaseStatusUpdateRequest,
    user: UserContext = Depends(require_role(["ADMIN", "VERIFICATION_OFFICER"]))
):
    try:
        updated = update_case_status(
            case_id=case_id,
            new_status=req.status,
            reason=req.reason,
            actor_id=user.user_id,
            actor_role=user.role,
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/cases/{case_id}/assign", response_model=CaseSchema)
def assign_case_officer(
    case_id: str,
    req: CaseAssignmentRequest,
    user: UserContext = Depends(require_role(["ADMIN", "VERIFICATION_OFFICER"]))
):
    try:
        updated = update_case_assignment(
            case_id=case_id,
            assigned_officer=req.assigned_officer,
            reason=req.reason,
            actor_id=user.user_id,
            actor_role=user.role,
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/cases/{case_id}/decision", response_model=CaseSchema)
def submit_case_decision(
    case_id: str,
    req: CaseDecisionRequest,
    user: UserContext = Depends(require_role(["ADMIN", "VERIFICATION_OFFICER"]))
):
    try:
        updated = record_case_decision(
            case_id=case_id,
            decision=req.decision,
            decision_reason=req.decision_reason,
            actor_id=user.user_id,
            actor_role=user.role,
            notes=req.notes,
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/cases/{case_id}/notes", response_model=CaseNoteSchema)
def add_note_to_case(
    case_id: str,
    req: CaseNoteRequest,
    user: UserContext = Depends(require_role(["ADMIN", "VERIFICATION_OFFICER"]))
):
    try:
        note = add_case_note(
            case_id=case_id,
            note_text=req.note_text,
            author_id=user.user_id,
            author_role=user.role,
        )
        return note
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/cases/{case_id}/audit-trail", response_model=List[CaseAuditEventSchema])
def get_case_audit_trail_endpoint(case_id: str):
    c = get_case_by_id(case_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    events = get_case_audit_trail(case_id)
    return [CaseAuditEventSchema(**e) for e in events]

# ==========================================================
# PHASE 2 & 3: TARIFFS, BILLING & PAYMENT ENDPOINTS
# ==========================================================

@app.get("/api/tariffs", response_model=List[TariffRuleSchema])
def get_tariffs_endpoint():
    """Returns all configured electricity tariff schedules."""
    return get_all_tariffs()

@app.put("/api/tariffs/{tariff_id}", response_model=TariffRuleSchema)
@app.post("/api/tariffs/{tariff_id}", response_model=TariffRuleSchema)
def update_tariff_endpoint(
    tariff_id: str,
    req: TariffRuleUpdateRequest,
    user: UserContext = Depends(require_role(["ADMIN"]))
):
    """Updates or creates a tariff rule. Restricted to Administrator role."""
    try:
        updated = create_or_update_tariff(
            tariff_id=tariff_id,
            tariff_name=req.tariff_name,
            effective_from=req.effective_from,
            rate_per_kwh_paise=req.rate_per_kwh_paise,
            fixed_charge_paise=req.fixed_charge_paise,
            effective_to=req.effective_to,
            currency=req.currency,
            is_active=req.is_active,
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/billing/summary", response_model=BillingSummaryResponse)
def get_billing_summary_endpoint():
    """Returns top-level KPIs for the demonstration billing & reconciliation sandbox."""
    return get_billing_summary_metrics()

@app.post("/api/billing/seed")
def seed_billing_endpoint(
    force: bool = Query(False),
    user: UserContext = Depends(require_role(["ADMIN"]))
):
    """Seeds synthetic bills and payment scenarios. Restricted to Administrator role."""
    return seed_billing_and_payments_if_empty(force=force)

@app.get("/api/billing/bills", response_model=SyntheticBillListResponse)
def list_synthetic_bills_endpoint(
    account_id: Optional[str] = None,
    meter_id: Optional[str] = None,
    scenario_label: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """Lists synthetic bills with optional filtering by account, meter, or scenario."""
    items, total = get_synthetic_bills(
        account_id=account_id,
        meter_id=meter_id,
        scenario_label=scenario_label,
        search=search,
        page=page,
        page_size=page_size,
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }

@app.get("/api/billing/bills/{bill_id}", response_model=SyntheticBillSchema)
def get_synthetic_bill_endpoint(bill_id: str):
    """Retrieves synthetic bill details by ID."""
    bill = get_synthetic_bill_by_id(bill_id)
    if not bill:
        raise HTTPException(status_code=404, detail=f"Bill '{bill_id}' not found.")
    return bill

@app.post("/api/billing/verify/{bill_id}", response_model=BillingVerificationResultSchema)
def verify_synthetic_bill_endpoint(
    bill_id: str,
    user: UserContext = Depends(require_role(["ADMIN", "VERIFICATION_OFFICER"]))
):
    """Runs the 4-step billing verification check against metered intervals and tariff rules."""
    try:
        res = verify_synthetic_bill(
            bill_id=bill_id,
            actor_id=user.user_id,
            actor_role=user.role,
            auto_create_case=True,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/billing/verification-history/{bill_id}", response_model=List[BillingVerificationResultSchema])
def get_billing_verification_history_endpoint(bill_id: str):
    """Returns historical verification runs for a given synthetic bill."""
    history = get_billing_verification_history(bill_id)
    return history

@app.get("/api/payments/transactions", response_model=List[SyntheticPaymentSchema])
def list_synthetic_payments_endpoint(
    account_id: Optional[str] = None,
    bill_id: Optional[str] = None,
    status: Optional[str] = None,
    unmatched_only: bool = Query(False),
):
    """Lists synthetic payments with filtering by account, bill reference, or settlement status."""
    txns = get_synthetic_payments(
        account_id=account_id,
        bill_id=bill_id,
        transaction_status=status,
        unmatched_only=unmatched_only,
    )
    return txns

@app.post("/api/payments/reconcile/{bill_id}", response_model=PaymentReconciliationResultSchema)
def reconcile_payments_endpoint(
    bill_id: str,
    user: UserContext = Depends(require_role(["ADMIN", "VERIFICATION_OFFICER"]))
):
    """Runs payment reconciliation for a bill against its matching and candidate transactions."""
    try:
        res = reconcile_bill_payments(
            bill_id=bill_id,
            actor_id=user.user_id,
            actor_role=user.role,
            auto_create_case=True,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/payments/reconciliation-history/{bill_id}", response_model=List[PaymentReconciliationResultSchema])
def get_payment_reconciliation_history_endpoint(bill_id: str):
    """Returns historical reconciliation runs for a given synthetic bill."""
    history = get_payment_reconciliation_history(bill_id)
    return history

@app.get("/api/billing-payments/discrepancies")
def get_billing_payment_discrepancies_endpoint():
    """Lists all active billing and payment discrepancy cases linked to the Review Queue."""
    cases_res = get_cases(category="BILLING_DISCREPANCY", page=1, page_size=100)
    recon_cases_res = get_cases(category="PAYMENT_RECONCILIATION", page=1, page_size=100)
    return {
        "billing_discrepancy_cases": cases_res["items"],
        "payment_discrepancy_cases": recon_cases_res["items"],
        "total_discrepancies": cases_res["total"] + recon_cases_res["total"],
    }

