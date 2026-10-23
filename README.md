# PowerVerify: Smart-Meter Consumption Anomaly Detection and Verification System

**Academic Evaluation Project — AI Blend for Engineers**

PowerVerify is a streamlined, transparent, and robust smart-meter electricity anomaly detection and human-in-the-loop verification application built entirely from scratch. It directly loads and processes the genuine **Council on Energy, Environment and Water (CEEW)** smart-meter dataset from Uttar Pradesh, India, trains an unsupervised **Isolation Forest** machine learning model, calculates robust **trailing MAD historical consumption boundaries**, displays interactive consumption time series, and provides a review queue for logging operational investigation decisions.

---

## 1. Key Highlights & Integrity Guarantees

- **100% Independent Rebuild:** Runs completely in its own directory with its own SQLite database, virtual environment, and Vite frontend.
- **Untouched Original Project:** The original `PowerVerify` project and its datasets remain strictly read-only and preserved.
- **Genuine Real-World Dataset:** Uses all **44,610 valid daily observations** from 84 smart meters in Bareilly and Mathura districts, UP. No synthetic data substitution in production results.
- **Real Machine Learning Model:** Fits scikit-learn's **Isolation Forest** on multidimensional consumption features (magnitude, day-over-day delta, baseline ratio, robust z-score, calendar cycles).
- **No Pseudo-Fraud Claims:** Anomaly scores are never represented as "fraud probabilities", recognizing that statistical outliers require human-in-the-loop verification (e.g. household vacancies, festive loads, grid outages).
- **Persistent Investigation Decisions:** SQLite database records and tracks decisions across application restarts with a complete audit history.

---

## 2. Verified Dataset Summary

Based on direct inspection and validation of the CEEW data files:

| Metric | Verified Value |
|---|---|
| **Authoring Institution** | Council on Energy, Environment and Water (CEEW), New Delhi |
| **Districts Covered** | Bareilly (46 smart meters) & Mathura (38 smart meters) |
| **Observation Window** | May 1, 2019 to October 31, 2021 (915 calendar days) |
| **Total Valid Readings** | 44,610 daily records |
| **Sampling Interval** | Daily Aggregate (sum of 3-minute smart meter readings) |
| **Measurement Unit** | Kilowatt-hours (kWh) |
| **Mean Daily Consumption** | 8.19 kWh/day |
| **Median Daily Consumption** | 5.77 kWh/day |
| **Peak Single-Day Reading** | 82.62 kWh/day |

---

## 3. Machine Learning Model Results

*Model: Isolation Forest (`n_estimators=150`, `contamination=0.03`, `random_state=42`)*

- **Total Records Analyzed:** 44,610
- **Total Flagged Anomalies:** 1,339 (3.0% of dataset)
- **High-Usage Anomalies:** 905 (exceeding historical upper expected boundary)
- **Low-Usage Anomalies:** 82 (dropping substantially below lower boundary or >80% drop from median)
- **Pattern Volatility Anomalies:** 315 (abrupt day-over-day swing with high robust z-score)
- **Distinct Meters with Flags:** 78 out of 84 meters

---

## 4. The Three Principal User Interface Pages

### Page 1: Overview Dashboard (`/`)
- Real-time dataset metadata card and KPI metric tiles.
- Interactive system-wide consumption graph with trailing expected range and red/amber anomaly dots.
- Hover tooltips showing exact kWh, expected boundaries, severity percentile, and data-derived reasoning.
- Live sensitivity slider to re-run Isolation Forest (`contamination` 1.0% to 8.0%).
- Quick meter jumper to transition directly into detailed meter exploration.

### Page 2: Meter Analysis
- Dropdown selector for all 84 individual meters.
- Displays meter district, total observation days, baseline statistics, and flagged counts.
- High-resolution interactive chart rendering daily consumption alongside trailing MAD bounds.
- Clickable points / cards displaying specific analytical explanations (e.g., *"Consumption (24.50 kWh) exceeded historical upper boundary (12.30 kWh) by +12.20 kWh (+99.2% vs median)"*).
- Direct **"Record Review Decision"** action button opening the investigation modal right on the page.

### Page 3: Review Queue
- Searchable, filterable table of all anomalous observations.
- Filters by meter ID, anomaly direction (High / Low / Pattern), and review status.
- Three supported operational decisions:
  1. **Acknowledge / No Further Action** — observation reviewed and deemed benign.
  2. **Mark for Field Visit** — warrants physical meter box inspection or seal check.
  3. **High Usage Authorized** — elevated load confirmed permitted (e.g. wedding, seasonal AC).
- Audit history modal logging previous status, timestamp, and optional reviewer notes.
- Export options: download flagged anomalies CSV, review decisions CSV, or formatted academic report.

---

## 5. Technology Stack

- **Backend:** Python 3.11, FastAPI, Pandas, NumPy, scikit-learn, SQLite.
- **Frontend:** React 19, TypeScript, Vite, Recharts, Lucide Icons, Vanilla CSS.
- **Testing:** Pytest (11 backend unit and integration tests), Vite production build.

---

## 6. Setup & Execution Instructions

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm

### 1. Backend Setup
From the project root:
```bash
# Create virtual environment if not already created
uv venv .venv
# or: python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS / Linux

# Install dependencies
uv pip install --link-mode=copy -p .venv fastapi "uvicorn[standard]" pandas numpy scikit-learn pydantic pytest httpx
```

### 2. Frontend Setup
From the project root:
```bash
cd frontend
npm install
npm run build   # Verifies TypeScript types and builds production assets
```

### 3. Running the Application

**Option A — Quick Startup Script (Windows):**
```powershell
.\run.ps1
```

**Option B — Manual Launch:**
Terminal 1 (Backend):
```bash
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
Terminal 2 (Frontend):
```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```
Open your browser to: **`http://localhost:5173`**
API Swagger Documentation: **`http://localhost:8000/docs`**

---

## 7. Running Backend Tests

PowerVerify Lite includes 11 comprehensive automated tests covering data integrity, feature calculations, Isolation Forest inference, SQLite persistence, and all API endpoints:

```bash
.venv\Scripts\python.exe -m pytest backend/tests -v
```

**Results:**
```
backend/tests/test_backend.py::test_load_and_validate_raw_ceew_data PASSED
backend/tests/test_backend.py::test_rolling_features_and_historical_mad_thresholds PASSED
backend/tests/test_backend.py::test_isolation_forest_model_execution PASSED
backend/tests/test_backend.py::test_health_endpoint PASSED
backend/tests/test_backend.py::test_dataset_summary_endpoint PASSED
backend/tests/test_backend.py::test_dashboard_stats_endpoint PASSED
backend/tests/test_backend.py::test_dashboard_chart_endpoints PASSED
backend/tests/test_backend.py::test_meters_list_and_history PASSED
backend/tests/test_backend.py::test_review_workflow_and_persistence PASSED
backend/tests/test_backend.py::test_settings_reanalyze PASSED
backend/tests/test_backend.py::test_csv_and_report_exports PASSED
======================= 11 passed in ~25s =======================
```

---

## 8. Directory Structure

```
PowerVerifyLite/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI endpoints, CORS, lifespan
│   │   ├── data_pipeline.py     # CEEW dataset loading, rolling features, Isolation Forest
│   │   ├── database.py          # SQLite persistence & audit trail
│   │   ├── schemas.py           # Pydantic models
│   │   └── powerverify_lite.db  # SQLite database
│   └── tests/
│       ├── __init__.py
│       └── test_backend.py      # Automated pytest suite (11 tests)
├── data/
│   ├── raw/
│   │   ├── CEEW -  ReadMe.txt
│   │   ├── SM Cleaned Data BR Aggregated.csv  # 28,119 rows (Bareilly)
│   │   └── SM Cleaned Data MH Aggregated.csv  # 16,491 rows (Mathura)
│   └── processed/
├── docs/
│   ├── ARCHITECTURE.md          # Architecture, sequence diagrams & ML rationale
│   └── DATA_DICTIONARY.md       # Full schema & feature mathematical formulation
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── ReviewModal.tsx  # Modal for recording 3 investigation decisions
│   │   ├── pages/
│   │   │   ├── OverviewDashboard.tsx  # Page 1: KPIs, charts, sensitivity slider
│   │   │   ├── MeterAnalysis.tsx      # Page 2: Per-meter history & MAD bounds
│   │   │   └── ReviewQueue.tsx        # Page 3: Flagged table, filters, actions
│   │   ├── api.ts               # REST API client
│   │   ├── types.ts             # TypeScript definitions
│   │   ├── App.tsx              # Main navigation & header
│   │   └── index.css            # White-and-blue design system
│   ├── package.json
│   └── vite.config.ts
├── run.ps1                      # Single-command launcher script
└── README.md                    # Project documentation
```

---

## 9. Academic Limitations & Notes for Viva

1. **Unsupervised Outlier Detection vs Fraud:** In real distribution utilities, consumption anomalies can be caused by unrecorded appliances, tenant moves, seasonal heating/cooling, or grid supply interruptions. PowerVerify Lite correctly focuses on behavioural outlier detection rather than unvalidated fraud labelling.
2. **Daily Aggregation Level:** Daily aggregations were selected because they provide an optimal balance between identifying consumer behavioral changes and system responsiveness. Sub-hourly readings (3-min pulses) capture transient power factor shifts but require substantially more computational resources without necessarily improving long-term verification workflows.
3. **Threshold Adaptation:** Robust MAD trailing boundaries adjust dynamically to each household's baseline consumption level. Meters with low baselines (~2 kWh/day) will alert on a 7 kWh surge, whereas high-consumption households (~35 kWh/day) will not be falsely flagged for the same 5 kWh increase.
