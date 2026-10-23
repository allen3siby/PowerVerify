import os
import glob
import uuid
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer

# Path resolutions
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

FEATURE_COLUMNS = ["kwh", "kwh_change", "baseline_ratio", "robust_z", "day_of_week"]

_pipeline_lock = threading.Lock()

def is_pipeline_running() -> bool:
    return _pipeline_lock.locked()

def validate_model_configuration(contamination: float, n_estimators: int = 150, random_state: int = 42):
    if contamination is None or not isinstance(contamination, (int, float)):
        raise ValueError("Contamination must be a numeric value.")
    if np.isnan(contamination) or np.isinf(contamination):
        raise ValueError("Contamination cannot be NaN or infinite.")
    if not (0.01 <= float(contamination) <= 0.08):
        raise ValueError(f"Contamination must be between 1.0% (0.01) and 8.0% (0.08). Received: {contamination}")
    if n_estimators is None or not isinstance(n_estimators, int) or n_estimators < 10 or n_estimators > 500:
        raise ValueError(f"n_estimators must be an integer between 10 and 500. Received: {n_estimators}")
    if random_state is None or not isinstance(random_state, int):
        raise ValueError("random_state must be an integer.")

class PipelineState:
    df_analyzed: Optional[pd.DataFrame] = None
    dataset_summary: Optional[Dict[str, Any]] = None
    model_metadata: Optional[Dict[str, Any]] = None
    contamination: float = 0.03
    n_estimators: int = 150
    random_state: int = 42
    active_run_id: Optional[str] = None
    last_error: Optional[str] = None

state = PipelineState()

def find_raw_files() -> List[str]:
    files = []
    br_file = os.path.join(DATA_RAW_DIR, "SM Cleaned Data BR Aggregated.csv")
    mh_file = os.path.join(DATA_RAW_DIR, "SM Cleaned Data MH Aggregated.csv")
    if os.path.exists(br_file):
        files.append(br_file)
    if os.path.exists(mh_file):
        files.append(mh_file)
    return files

def load_and_validate_raw_data() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    raw_files = find_raw_files()
    if not raw_files:
        raise FileNotFoundError(f"No CEEW aggregated CSV files found in {DATA_RAW_DIR}")

    frames = []
    total_raw_rows = 0
    quarantined_count = 0
    duplicate_count = 0

    for file_path in raw_files:
        filename = os.path.basename(file_path)
        district = "Bareilly" if "BR" in filename else "Mathura"
        
        df_chunk = pd.read_csv(file_path)
        total_raw_rows += len(df_chunk)

        # Standardize column names
        df_chunk.columns = [c.strip() for c in df_chunk.columns]
        if "meter" not in df_chunk.columns or "Date" not in df_chunk.columns or "t_kWh" not in df_chunk.columns:
            raise ValueError(f"Unexpected schema in {filename}: {list(df_chunk.columns)}")

        # Clean string meter ID and dates
        df_chunk["meter_id"] = df_chunk["meter"].astype(str).str.strip()
        df_chunk["date_parsed"] = pd.to_datetime(df_chunk["Date"], errors="coerce")
        df_chunk["kwh"] = pd.to_numeric(df_chunk["t_kWh"], errors="coerce")
        df_chunk["district"] = district

        # Quarantine check
        invalid_mask = df_chunk["date_parsed"].isna() | df_chunk["kwh"].isna() | (df_chunk["kwh"] < 0)
        quarantined_count += int(invalid_mask.sum())
        clean_chunk = df_chunk[~invalid_mask].copy()

        # Duplicate check on (meter_id, date)
        dup_mask = clean_chunk.duplicated(subset=["meter_id", "date_parsed"], keep="first")
        duplicate_count += int(dup_mask.sum())
        clean_chunk = clean_chunk[~dup_mask].copy()

        frames.append(clean_chunk)

    combined_df = pd.concat(frames, ignore_index=True)
    combined_df["date"] = combined_df["date_parsed"].dt.strftime("%Y-%m-%d")
    combined_df.sort_values(by=["meter_id", "date_parsed"], inplace=True)
    combined_df.reset_index(drop=True, inplace=True)

    summary = {
        "dataset_name": "CEEW Uttar Pradesh Smart Meter Study (Mathura & Bareilly)",
        "source_institution": "Council on Energy, Environment and Water (CEEW)",
        "sampling_interval": "Daily Aggregate (sum of 3-minute smart meter readings)",
        "measurement_unit": "kWh (electricity consumption)",
        "raw_files": [os.path.basename(f) for f in raw_files],
        "total_raw_rows": total_raw_rows,
        "valid_readings": len(combined_df),
        "quarantined_readings": quarantined_count,
        "duplicate_readings": duplicate_count,
        "total_meters": int(combined_df["meter_id"].nunique()),
        "meters_list": sorted(combined_df["meter_id"].unique().tolist()),
        "districts": sorted(combined_df["district"].unique().tolist()),
        "start_date": str(combined_df["date"].min()),
        "end_date": str(combined_df["date"].max()),
        "mean_kwh": float(round(combined_df["kwh"].mean(), 3)),
        "median_kwh": float(round(combined_df["kwh"].median(), 3)),
        "min_kwh": float(round(combined_df["kwh"].min(), 3)),
        "max_kwh": float(round(combined_df["kwh"].max(), 3)),
    }

    return combined_df, summary

def calculate_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes trailing statistical baselines and features strictly per meter.
    Uses rolling 30-day window to prevent future data leakage.
    """
    processed_groups = []

    for meter_id, group in df.groupby("meter_id", sort=False):
        g = group.copy().sort_values("date_parsed")
        
        # Lag consumption
        g["prev_kwh"] = g["kwh"].shift(1)
        g["kwh_change"] = g["kwh"] - g["prev_kwh"]
        g["kwh_change"] = g["kwh_change"].fillna(0.0)

        # Calendar features
        g["day_of_week"] = g["date_parsed"].dt.dayofweek
        g["is_weekend"] = g["day_of_week"].isin([5, 6]).astype(int)
        g["month"] = g["date_parsed"].dt.month

        # Rolling 30-day trailing statistics (min 5 observations for meaningful baseline)
        rolling_series = g["kwh"].rolling(window=30, min_periods=5)
        g["trailing_median"] = rolling_series.median()
        
        # Rolling MAD: median(|x - rolling_median|)
        # Compute efficiently
        def calc_mad(window_vals):
            med = np.median(window_vals)
            return np.median(np.abs(window_vals - med))

        g["trailing_mad"] = g["kwh"].rolling(window=30, min_periods=5).apply(calc_mad, raw=True)
        
        # Default fallback for initial observations or zero MAD
        meter_overall_median = g["kwh"].median()
        meter_overall_mad = np.median(np.abs(g["kwh"] - meter_overall_median)) or 0.5
        
        g["trailing_median"] = g["trailing_median"].fillna(meter_overall_median)
        g["trailing_mad"] = g["trailing_mad"].fillna(meter_overall_mad)
        g["trailing_mad"] = np.where(g["trailing_mad"] < 0.05, 0.05, g["trailing_mad"])

        # Insufficient history flag (< 7 observations so far)
        g["obs_index"] = np.arange(len(g))
        g["insufficient_history"] = g["obs_index"] < 7

        # Robust scale = 1.4826 * MAD (asymptotically normal consistent estimator)
        scale = 1.4826 * g["trailing_mad"]
        g["expected_upper"] = np.round(g["trailing_median"] + 2.5 * scale, 3)
        g["expected_lower"] = np.round(np.maximum(0.0, g["trailing_median"] - 2.5 * scale), 3)

        # Baseline ratio & robust z
        safe_med = np.maximum(g["trailing_median"], 0.05)
        g["baseline_ratio"] = np.round(g["kwh"] / safe_med, 3)
        g["robust_z"] = np.round((g["kwh"] - g["trailing_median"]) / scale, 3)

        processed_groups.append(g)

    return pd.concat(processed_groups, ignore_index=True)

def fit_isolation_forest(
    df: pd.DataFrame,
    contamination: float = 0.03,
    n_estimators: int = 150,
    random_state: int = 42
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Fits Isolation Forest unsupervised anomaly detector on robust multi-feature representation.
    """
    X = df[FEATURE_COLUMNS].copy()
    
    # Impute initial NaNs if any
    imputer = SimpleImputer(strategy="median")
    X_imputed = imputer.fit_transform(X)

    iso_forest = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1
    )
    
    iso_forest.fit(X_imputed)
    raw_scores = iso_forest.score_samples(X_imputed)  # Higher is normal, lower is anomalous
    anomaly_scores = -raw_scores  # Higher is anomalous

    # Empirical percentile normalization (0 to 1)
    ranks = pd.Series(anomaly_scores).rank(pct=True).to_numpy()

    # sklearn binary prediction (-1 = anomaly, 1 = normal)
    preds = iso_forest.predict(X_imputed)
    iso_anom_mask = (preds == -1)

    result_df = df.copy()
    result_df["anomaly_score_raw"] = np.round(anomaly_scores, 4)
    result_df["anomaly_severity"] = np.round(ranks, 4)
    result_df["anomaly_score"] = np.round(ranks, 4)
    result_df["observation_id"] = result_df["meter_id"] + "_" + result_df["date"]
    result_df["observed_consumption"] = result_df["kwh"]

    # Statistical boundaries evaluation
    # High: observed > expected_upper
    # Low: observed < expected_lower
    stat_high_mask = (result_df["kwh"] > result_df["expected_upper"])
    stat_low_mask = (result_df["kwh"] < result_df["expected_lower"])
    stat_anom_mask = stat_high_mask | stat_low_mask

    # Combined authoritative anomaly policy:
    # An observation is anomalous if it breaches the statistical threshold OR if the multi-feature Isolation Forest flags it.
    combined_anom_mask = stat_anom_mask | iso_anom_mask

    result_df["statistical_anomaly"] = stat_anom_mask
    result_df["isolation_forest_anomaly"] = iso_anom_mask
    result_df["is_anomaly"] = combined_anom_mask

    # Classify direction & generate data-derived explanation
    directions = []
    detection_methods = []
    reasons = []

    for _, row in result_df.iterrows():
        val = row["kwh"]
        med = row["trailing_median"]
        upper = row["expected_upper"]
        lower = row["expected_lower"]
        is_stat = row["statistical_anomaly"]
        is_iso = row["isolation_forest_anomaly"]
        is_sparse = row["insufficient_history"]
        delta = row["kwh_change"]
        sparse_note = " (provisional baseline: < 7 historical readings)" if is_sparse else ""

        pct = ((val - med) / max(med, 0.05)) * 100 if val >= med else ((med - val) / max(med, 0.05)) * 100

        if val > upper:
            directions.append("high")
            if is_iso:
                detection_methods.append("STATISTICAL_AND_ML")
                reasons.append(
                    f"High Usage Anomaly (Statistical Threshold & Isolation Forest): Consumption ({val:.2f} kWh) "
                    f"exceeded historical upper boundary ({upper:.2f} kWh) by +{val - upper:.2f} kWh (+{pct:.1f}% vs median){sparse_note}."
                )
            else:
                detection_methods.append("STATISTICAL_MAD")
                reasons.append(
                    f"High Usage Anomaly (Statistical Boundary Breach): Consumption ({val:.2f} kWh) "
                    f"exceeded historical upper boundary ({upper:.2f} kWh) by +{val - upper:.2f} kWh (+{pct:.1f}% vs median){sparse_note}."
                )
        elif val < lower:
            directions.append("low")
            if is_iso:
                detection_methods.append("STATISTICAL_AND_ML")
                reasons.append(
                    f"Low Usage Anomaly (Statistical Threshold & Isolation Forest): Consumption ({val:.2f} kWh) "
                    f"dropped significantly below expected lower boundary ({lower:.2f} kWh, -{pct:.1f}% vs median){sparse_note}."
                )
            else:
                detection_methods.append("STATISTICAL_MAD")
                reasons.append(
                    f"Low Usage Anomaly (Statistical Boundary Breach): Consumption ({val:.2f} kWh) "
                    f"dropped significantly below expected lower boundary ({lower:.2f} kWh, -{pct:.1f}% vs median){sparse_note}."
                )
        elif is_iso:
            # Multi-feature anomaly within univariate bounds -> Pattern Anomaly
            directions.append("pattern")
            detection_methods.append("ISOLATION_FOREST_PATTERN")
            reasons.append(
                f"Pattern Anomaly (Multidimensional Outlier): Consumption ({val:.2f} kWh) is within statistical range "
                f"({lower:.2f} - {upper:.2f} kWh), but exhibits atypical multidimensional behavior: "
                f"day change {delta:+.2f} kWh, robust z-score {row['robust_z']:.2f}{sparse_note}."
            )
        else:
            directions.append("normal")
            detection_methods.append("NORMAL")
            if is_sparse:
                reasons.append(
                    f"Normal ({val:.2f} kWh): within provisional historical bounds ({lower:.2f} - {upper:.2f} kWh){sparse_note}."
                )
            else:
                reasons.append(
                    f"Normal ({val:.2f} kWh): consumption is within expected historical bounds ({lower:.2f} - {upper:.2f} kWh)."
                )

    result_df["anomaly_direction"] = directions
    result_df["detection_method"] = detection_methods
    result_df["reason"] = reasons

    model_metadata = {
        "model_name": "Isolation Forest (scikit-learn)",
        "algorithm_family": "Ensemble Hybrid: Unsupervised Outlier Forest & Trailing Median/MAD Bounds",
        "contamination": contamination,
        "n_estimators": n_estimators,
        "random_state": random_state,
        "features_used": FEATURE_COLUMNS,
        "total_records": len(result_df),
        "total_anomalies": int(iso_anom_mask.sum()),
        "combined_anomalies": int(combined_anom_mask.sum()),
        "statistical_anomalies": int(stat_anom_mask.sum()),
        "isolation_forest_anomalies": int(iso_anom_mask.sum()),
        "high_usage_anomalies": int((result_df["anomaly_direction"] == "high").sum()),
        "low_usage_anomalies": int((result_df["anomaly_direction"] == "low").sum()),
        "pattern_anomalies": int((result_df["anomaly_direction"] == "pattern").sum()),
        "anomaly_percentage": float(round((iso_anom_mask.sum() / len(result_df)) * 100, 2)),
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
    }

    return result_df, model_metadata

def run_pipeline(
    contamination: Optional[float] = None,
    n_estimators: Optional[int] = None,
    random_state: Optional[int] = None,
    force_reload: bool = False,
    run_id: Optional[str] = None,
    dataset_fingerprint: str = "CEEW_UP_2021"
) -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any]]:
    """
    Coordinates end-to-end pipeline execution with thread safety, SQLite persistence,
    and non-destructive error handling.
    """
    global state

    target_contamination = float(contamination) if contamination is not None else state.contamination
    target_n_estimators = int(n_estimators) if n_estimators is not None else state.n_estimators
    target_random_state = int(random_state) if random_state is not None else state.random_state

    # Validate parameters strictly
    validate_model_configuration(target_contamination, target_n_estimators, target_random_state)

    if (
        not force_reload
        and state.df_analyzed is not None
        and abs(state.contamination - target_contamination) < 1e-6
        and state.n_estimators == target_n_estimators
        and state.random_state == target_random_state
    ):
        return state.df_analyzed, state.dataset_summary, state.model_metadata

    # Acquire lock with timeout for concurrent execution safety
    acquired = _pipeline_lock.acquire(blocking=True, timeout=120)
    if not acquired:
        raise RuntimeError("Model pipeline execution is already in progress by another task.")

    cur_run_id = run_id or f"MRUN-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

    try:
        from backend.app.database import (
            record_model_run_start,
            record_model_run_completed,
            record_model_run_failed,
            save_active_model_config,
        )

        record_model_run_start(
            run_id=cur_run_id,
            contamination=target_contamination,
            n_estimators=target_n_estimators,
            random_state=target_random_state,
            model_name="Isolation Forest (scikit-learn)",
            features_used=FEATURE_COLUMNS,
            dataset_fingerprint=dataset_fingerprint
        )

        # 1. Load and clean CEEW data
        raw_df, dataset_summary = load_and_validate_raw_data()

        # 2. Extract trailing features & thresholds
        featured_df = calculate_rolling_features(raw_df)

        # 3. Fit Isolation Forest and score anomalies
        analyzed_df, model_metadata = fit_isolation_forest(
            featured_df,
            contamination=target_contamination,
            n_estimators=target_n_estimators,
            random_state=target_random_state
        )

        model_metadata["run_id"] = cur_run_id
        model_metadata["dataset_fingerprint"] = dataset_fingerprint

        flagged_ids = analyzed_df[analyzed_df["isolation_forest_anomaly"]]["observation_id"].tolist()

        # Record completion in database
        record_model_run_completed(
            run_id=cur_run_id,
            records_analyzed=len(analyzed_df),
            anomalies_flagged=int(analyzed_df["isolation_forest_anomaly"].sum()),
            high_anomalies=int((analyzed_df["anomaly_direction"] == "high").sum()),
            low_anomalies=int((analyzed_df["anomaly_direction"] == "low").sum()),
            pattern_anomalies=int((analyzed_df["anomaly_direction"] == "pattern").sum()),
            statistical_anomalies=int(analyzed_df["statistical_anomaly"].sum()),
            features_used=FEATURE_COLUMNS,
            flagged_ids=flagged_ids,
            dataset_fingerprint=dataset_fingerprint,
            set_active=True
        )

        # Persist active configuration to database
        save_active_model_config(
            contamination=target_contamination,
            n_estimators=target_n_estimators,
            random_state=target_random_state,
            active_run_id=cur_run_id
        )

        # Update in-memory state ONLY on complete success
        state.df_analyzed = analyzed_df
        state.dataset_summary = dataset_summary
        state.model_metadata = model_metadata
        state.contamination = target_contamination
        state.n_estimators = target_n_estimators
        state.random_state = target_random_state
        state.active_run_id = cur_run_id
        state.last_error = None

        return analyzed_df, dataset_summary, model_metadata

    except Exception as e:
        state.last_error = str(e)
        try:
            from backend.app.database import record_model_run_failed
            record_model_run_failed(cur_run_id, str(e))
        except Exception:
            pass
        # Preserve previous successful state.df_analyzed without partial overwrite!
        raise
    finally:
        _pipeline_lock.release()

def init_pipeline_from_saved_config() -> Tuple[pd.DataFrame, Dict[str, Any], Dict[str, Any]]:
    """
    Called at application startup to load persisted configuration from SQLite
    and initialize pipeline state.
    """
    from backend.app.database import get_active_model_config

    cfg = get_active_model_config()
    saved_contam = cfg.get("contamination", 0.03)
    saved_trees = cfg.get("n_estimators", 150)
    saved_seed = cfg.get("random_state", 42)

    return run_pipeline(
        contamination=saved_contam,
        n_estimators=saved_trees,
        random_state=saved_seed,
        force_reload=True
    )
