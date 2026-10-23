# PowerVerify: System Architecture & Workflow

PowerVerify is an academic-grade smart-meter electricity consumption anomaly detection and verification system built from scratch for the **AI Blend for Engineers** academic evaluation.

---

## 1. High-Level Architecture Diagram

```mermaid
graph TD
    A["Raw CEEW Dataset<br/>(Bareilly & Mathura CSVs, 44,610 rows)"] --> B["Data Pipeline & Integrity Engine<br/>(Schema validation, timestamp sorting, deduplication)"]
    B --> C["Feature Engineering Engine<br/>(Trailing 30d Median, MAD bounds, delta, calendar)"]
    C --> D["Machine Learning Engine<br/>(Isolation Forest, contamination=0.03, 150 trees)"]
    D --> E["In-Memory Analytics Cache"]
    
    E --> F["FastAPI REST Backend<br/>(Endpoints on :8000)"]
    G["SQLite Database<br/>(powerverify_lite.db)"] <--> F
    
    F <--> H["Vite + React + TypeScript Frontend<br/>(Interactive UI on :5173)"]
    
    subgraph UI_Pages ["Three Principal Interface Views"]
        H1["1. Overview Dashboard<br/>KPIs, System Mean & Anomaly Chart, Sensitivity Tuning"]
        H2["2. Meter Analysis<br/>Per-Meter Trailing MAD Bounds, Anomaly Markers, Deep Inspection"]
        H3["3. Review Queue<br/>Filterable Queue, Investigation Actions, Audit History, Exports"]
    end
    H --> H1
    H --> H2
    H --> H3
```

---

## 2. End-to-End Operational Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User as Engineer / Reviewer
    participant FE as React Frontend (Vite)
    participant BE as FastAPI Backend
    participant Pipe as Pipeline & Isolation Forest
    participant DB as SQLite DB

    User->>FE: Open Overview Dashboard
    FE->>BE: GET /api/dataset/summary & GET /api/dashboard/stats
    BE->>Pipe: Run pipeline (cached after first run)
    Pipe-->>BE: Return 44,610 analyzed readings & 1,339 anomalies
    BE->>DB: Query current observation statuses
    BE-->>FE: Return KPIs & aggregated consumption time series
    FE-->>User: Render interactive charts with red/amber markers

    User->>FE: Select Meter (e.g. BR36) for Inspection
    FE->>BE: GET /api/meters/BR36/history
    BE-->>FE: Return time series with dynamic trailing MAD boundaries
    FE-->>User: Display chart + data-derived analytical explanation

    User->>FE: Click 'Review' and choose 'Mark for Field Visit'
    FE->>BE: POST /api/reviews (decision, notes)
    BE->>DB: Update observation_status & insert review_decisions record
    DB-->>BE: Persistence confirmed
    BE-->>FE: Success response
    FE-->>User: Badge updates to 'Field Visit' across Queue & Meter views

    User->>FE: Click 'Export Flagged CSV' / 'Academic Report'
    FE->>BE: GET /api/export/csv?flagged_only=true
    BE-->>FE: Stream generated CSV containing real model outputs
    FE-->>User: File downloaded to browser
```

---

## 3. Machine Learning Methodology Rationale

### Why Isolation Forest?
1. **Unsupervised Formulation:** The CEEW smart-meter dataset contains real, unlabelled household meter consumption. No confirmed fraud or tampering labels exist. Supervised algorithms (e.g. Random Forest classifier, XGBoost) would require fabricating ground truth labels or relying on synthetic tampering assumptions. Isolation Forest makes zero fraud assumptions and identifies behavioural outliers strictly through data isolation depth.
2. **Sub-sampling & Efficiency:** By isolating points through random axis-aligned splits, anomalies (which have extreme consumption or abnormal ratios) are separated near the root of the tree with short average path lengths:
   $$s(x, n) = 2^{-\frac{E(h(x))}{c(n)}}$$
   Where $E(h(x))$ is the average path length across 150 isolation trees, and $c(n)$ is the average path length of unsuccessful searches in a Binary Search Tree.
3. **Multi-Feature Context:** Rather than looking only at absolute kWh, the model evaluates multidimensional dynamics:
   - Consumption magnitude (`kwh`)
   - Day-over-day volatility (`kwh_change`)
   - Trailing baseline ratio (`baseline_ratio`)
   - Robust standardized deviation (`robust_z`)
   - Weekly cycle (`day_of_week`)

---

## 4. Historical Expected Threshold Methodology (Robust MAD)

Standard deviation is heavily distorted by the very anomalies we wish to detect (a single 80 kWh spike inflates the sample standard deviation). PowerVerify Lite instead implements **Median Absolute Deviation (MAD)**:

$$\text{MAD} = \text{Median}(\|x_i - \text{Median}(X)\|)$$

To match the standard normal scale, the consistent scale estimator is:
$$\hat{\sigma}_{\text{robust}} = 1.4826 \times \text{MAD}$$

The expected consumption band is defined as:
$$\text{Upper Bound} = \text{Median} + 2.5 \times \hat{\sigma}_{\text{robust}}$$
$$\text{Lower Bound} = \max\left(0.0, \text{Median} - 2.5 \times \hat{\sigma}_{\text{robust}}\right)$$

### Prevention of Data Leakage
All medians and MAD values are computed over a **trailing 30-day window** preceding and including the day of observation. Future readings never influence past baselines.

---

## 5. Three Standard Investigation Decisions

To provide an intuitive, human-in-the-loop workflow without pseudo-fraud jargon:

1. **Acknowledge / No Further Action:** Observation has been reviewed and determined to be benign or explainable without dispatching personnel.
2. **Mark for Field Visit:** Observation exhibits severe drop, erratic zero-consumption, or unpermitted surge warranting physical inspection of the meter box, seal integrity, and wiring.
3. **High Usage Authorized:** Observation reflects verified permitted demand (e.g. household wedding, construction equipment, or approved seasonal load).

---

## 6. Critical Ethical & Academic Boundary

- **Anomalies $\neq$ Proven Theft:** Statistical outliers indicate unusual consumption, NOT confirmed electricity theft.
- Low-usage anomalies frequently stem from household vacancies, supply outages, or CT/PT telemetry failure.
- High-usage anomalies frequently stem from festive events, air conditioning during summer heat waves, or additional household occupants.
- Human-in-the-loop verification is mandatory before taking punitive or administrative action.
