# PowerVerify Lite: Data Dictionary

## 1. Verified Source Dataset Details

| Attribute | Specification |
|---|---|
| **Study Name** | What Smart Meters Can Tell Us: Insights on Electricity Supply and Use in Mathura and Bareilly Households |
| **Institution** | Council on Energy, Environment and Water (CEEW), New Delhi, India |
| **Principal Authors** | Shalu Agrawal, Sunil Mani, Abhishek Jain, Karthik Ganesan |
| **Geographic Scope** | Bareilly (BR) and Mathura (MH) Districts, Uttar Pradesh, India |
| **Observation Window** | May 1, 2019 to October 31, 2021 (915 calendar days) |
| **Meter Count** | 84 Distinct Smart Meters (46 in Bareilly, 38 in Mathura) |
| **Total Daily Records** | 44,610 valid daily observations |
| **Measurement Unit** | Kilowatt-hours (kWh) — daily interval electricity consumption |
| **Telemetry Resolution** | Aggregated daily from raw 3-minute smart meter pulses |

---

## 2. Source Data Attributes (Input Schema)

| Field Name | Type | Unit | Description |
|---|---|---|---|
| `meter` | String (Categorical) | N/A | Smart meter alphanumeric identifier (e.g., `BR02` to `BR52`, `MH01` to `MH47`). |
| `Date` | String (`YYYY-MM-DD`) | Date | Date of observation. |
| `t_kWh` | Float64 | kWh | Total electricity consumed during that calendar day. Derived as the direct sum of 3-minute interval readings. Ranges from 0.000 to 82.622 kWh/day. |

---

## 3. Preprocessing & Feature Pipeline (Engineered Schema)

Features are constructed chronologically per meter without future data leakage:

| Feature Name | Type | Unit | Formulation / Mathematical Definition | Purpose in Anomaly Detection |
|---|---|---|---|---|
| `kwh` | Float64 | kWh | $x_t = \text{t\_kWh}$ | Current day's electricity consumption. |
| `prev_kwh` | Float64 | kWh | $x_{t-1}$ (lag 1 day) | Prior day's consumption baseline. |
| `kwh_change` | Float64 | kWh | $\Delta x_t = x_t - x_{t-1}$ | Day-over-day delta to capture sudden surges or drops. |
| `trailing_median` | Float64 | kWh | $\text{Median}(x_{t-29}, \dots, x_t)$ (trailing 30 days) | Non-parametric central tendency, resistant to extreme spikes. |
| `trailing_mad` | Float64 | kWh | $\text{Median}(\|x_i - \text{trailing\_median}\|)$ | Median Absolute Deviation; robust scale estimator. |
| `expected_upper` | Float64 | kWh | $\text{trailing\_median} + 2.5 \times (1.4826 \times \text{trailing\_mad})$ | Upper expected consumption boundary. |
| `expected_lower` | Float64 | kWh | $\max(0.0, \text{trailing\_median} - 2.5 \times (1.4826 \times \text{trailing\_mad}))$ | Lower expected consumption boundary. |
| `baseline_ratio` | Float64 | Ratio | $x_t / \max(\text{trailing\_median}, 0.05)$ | Relative magnitude compared to household typical use. |
| `robust_z` | Float64 | Z-Score | $(x_t - \text{trailing\_median}) / (1.4826 \times \text{trailing\_mad} + 10^{-4})$ | Standardized robust distance from normal profile. |
| `day_of_week` | Int32 | Index | $0 = \text{Monday}, \dots, 6 = \text{Sunday}$ | Weekly behavioral patterns (weekdays vs weekends). |
| `is_weekend` | Int32 | Binary | $1 \text{ if Saturday/Sunday else } 0$ | Household weekend lifestyle variation. |
| `month` | Int32 | Index | $1 = \text{Jan}, \dots, 12 = \text{Dec}$ | Seasonal heating/cooling demand (UP summer heat waves). |
| `insufficient_history` | Boolean | Flag | $\text{True if meter has } < 7 \text{ historical days}$ | Flags provisional baselines to avoid premature alerts. |

---

## 4. Machine Learning Model Output Schema

| Field Name | Type | Range / Domain | Definition & Meaning |
|---|---|---|---|
| `raw_score` | Float64 | $(-\infty, 0]$ | Scikit-learn Isolation Forest `score_samples(X)`. Higher means more normal. |
| `anomaly_score` | Float64 | $[0, \infty)$ | Inverted score: $-\text{raw\_score}$. Higher indicates greater anomalousness. |
| `anomaly_severity` | Float64 | $[0.0, 1.0]$ | Empirical percentile rank of `anomaly_score` across dataset. |
| `is_anomaly` | Boolean | True / False | Binary flag determined by contamination threshold cut. |
| `anomaly_direction` | String | `high`, `low`, `pattern`, `normal` | Directional classification derived by comparing observed kWh against robust bounds. |
| `reason` | String | Text | Data-derived human-readable explanation of why the observation was flagged. |

---

## 5. Persistence & Review Schema (SQLite)

| Field Name | Table | Type | Purpose |
|---|---|---|---|
| `observation_id` | `observation_status`, `review_decisions` | TEXT PRIMARY KEY | Composite key: `{meter_id}_{YYYY-MM-DD}` (e.g. `BR02_2020-04-15`). |
| `current_status` | `observation_status` | TEXT | `Pending Review`, `Acknowledge / No Further Action`, `Mark for Field Visit`, `High Usage Authorized`. |
| `decision` | `review_decisions` | TEXT | Specific action logged during verification. |
| `notes` | `review_decisions` | TEXT | Optional inspector / investigator notes. |
| `previous_status` | `review_decisions` | TEXT | Prior review status before this decision. |
| `new_status` | `review_decisions` | TEXT | Updated review status resulting from decision. |
| `created_at` | `review_decisions` | TEXT | ISO 8601 UTC timestamp of decision. |
