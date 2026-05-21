# TeleSight 🔍


## What is TeleSight?

TeleSight is an agentic AI system that reads telecom churn data from multiple sources, reasons about it using a structured LangGraph pipeline powered by Gemini 2.5 Flash, and autonomously executes a retention action chain — all without human intervention.

The agent ingests 5 data sources simultaneously, detects churn patterns across 3 months of data, flags contradictions between sources, calculates revenue impact, applies real-world constraints, and simulates a full retention campaign — including failure recovery and rollback.

---

## How It Works

```
5 Data Sources (APIs)
        ↓
FastAPI Upload Endpoint
        ↓
LangGraph Agent Pipeline (5 nodes)
  ├── Node 1: Ingest & validate
  ├── Node 2: Temporal analysis (3-month trends)
  ├── Node 3: Contradiction detection (cross-source)
  ├── Node 4: Insight & revenue impact
  └── Node 5: Constraint-based action planning
        ↓
Action Execution Layer (5 actions)
  ├── Action 1: Diagnose root cause
  ├── Action 2: Notify regional manager
  ├── Action 3: Update CRM (simulated failure + rollback)
  ├── Action 4: Launch SMS campaign (constraint-batched)
  └── Action 5: Schedule 7-day follow-up monitor
        ↓
Outcome stored in MongoDB
(before/after state, campaign record, action logs)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | LangGraph (Python) |
| LLM | Gemini 2.5 Flash via Google Vertex AI |
| Orchestration | Google Antigravity |
| Backend API | FastAPI (Python) |
| File Parsing | pdfplumber + pandas |
| Database | MongoDB Atlas |
| Mobile App | (not built yet) |

---

## The 5 Data Sources

All inputs are fetched via API calls — no local file reads in the default mode.

| Input | Source | Type |
|---|---|---|
| Churn data | `/mock-api/churn-data` (self-hosted) | Simulated a CRM API |
| Monthly report | `/mock-api/monthly-report` (self-hosted) | Simulated a Reports API |
| KPI dashboard | World Bank Open Data API | Real external API |
| Competitor news | NewsAPI.org | Real external API |
| Live signals | Wikipedia Recent Changes API | Real external API (with fallback) |

Users can also upload their own CSV and PDF files via the custom upload mode — the agent adjusts all reasoning and outputs to the new data automatically.

---

## Agent Pipeline — Node by Node

### Node 1 — Ingest
Confirms all data is present in the pipeline state. Updates run status to `processing` in MongoDB. Entry point of the LangGraph graph.

### Node 2 — Temporal Analysis
Analyzes customer data across 3 months to detect trend direction. Computes:
- Average data usage drop month-over-month
- Percentage of customers with no recharge in 30+ days
- Highest risk region by customer count
- Overall trend: `accelerating` / `stable` / `improving`

### Node 3 — Contradiction Detection
Cross-references all text sources (PDF report, news articles) against the CSV churn signals. Flags conflicts where positive sentiment in narrative sources contradicts high churn in operational data. Scores each source by credibility (CSV: 0.91, external text: 0.54). Calls Gemini to explain the conflict and suggest an investigation path.

### Node 4 — Insight & Impact
Produces the core business insight from cleaned CSV data:
- Total high-risk customer count
- Regional breakdown
- Average days without recharge for at-risk segment
- Average complaints per at-risk customer
- Projected revenue loss (ARPU × high-risk count × churn conversion rate)
- Severity classification: `critical` / `high` / `medium`

Calls Gemini for a plain-English business explanation contextualised to Pakistani telecom market conditions.

### Node 5 — Constraint-Based Action Planning
Applies real-world constraints before generating the action plan:
- Budget cap: PKR 50,000
- Cost per SMS: PKR 25 → max 2,000 SMS affordable
- Rate limit: 500 SMS/hour → 4 batches required
- Time window: 48 hours

Generates a 5-step action plan. Calls Gemini to write a personalized SMS template for Pakistani prepaid customers.

---

## Action Execution Layer

After the pipeline completes, the execution layer fires all 5 actions sequentially.

### Action 1 — Diagnose Cause
Reads `insight_report` and writes a structured diagnosis to `action_logs`. Documents the primary churn driver before any action is taken.

### Action 2 — Notify Manager
Builds a manager alert with region, customer count, projected loss, severity, and recommended action. Written to `action_logs` as a simulated notification.

### Action 3 — Update CRM *(deliberate failure)*
Simulates a CRM API call that returns HTTP 500. The agent:
1. Logs the failure
2. Waits 2 seconds
3. Retries once
4. Fails again
5. Rolls back state
6. Marks as `rolled_back`
7. Continues to Action 4

This demonstrates the failure recovery requirement explicitly.

### Action 4 — Launch SMS Campaign
Creates a real campaign record in the `campaigns` MongoDB collection:
- Targets 2,000 customers (budget-constrained from 3,200)
- Batches into 4 groups of 500 SMS/hour
- Uses Gemini-generated personalized SMS template
- Stores full batch schedule with timestamps

### Action 5 — Schedule Follow-Up Monitor
Creates a monitoring task in `action_logs` set to fire 7 days after campaign launch. Tracks recharge rate among targeted customers. Escalates if less than 40% respond.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server health check |
| `GET` | `/mock-api/churn-data` | Simulated Telenor CRM API — returns metadata + sample |
| `GET` | `/mock-api/monthly-report` | Simulated Telenor Reports API — returns PDF text |
| `POST` | `/api/upload` | Fetch all 5 inputs, store to MongoDB, return `run_id` |
| `POST` | `/api/pipeline/run/{run_id}` | Trigger full LangGraph pipeline for a run |
| `GET` | `/api/pipeline/status/{run_id}` | Poll current pipeline status |
| `GET` | `/api/feed/live` | Returns one fresh live churn signal event |
| `POST` | `/api/actions/execute/{run_id}` | Execute all 5 actions sequentially |
| `GET` | `/api/actions/logs/{run_id}` | Fetch all action logs for a run |

---

## MongoDB Collections

### `pipeline_status`
One document per pipeline run. Tracks status from ingestion through completion.

```json
{
  "run_id": "uuid",
  "status": "complete",
  "current_step": "complete",
  "ingested_data": { "csv_records_count": 5000, "..." },
  "temporal_analysis": { "..." },
  "contradiction_report": { "conflict_detected": true, "..." },
  "insight_report": { "total_high_risk_customers": 3200, "..." },
  "action_plan": { "constraints_applied": {}, "actions": [] },
  "outcome": { "before_state": {}, "after_state": {}, "..." },
  "data_sources": [],
  "created_at": "timestamp"
}
```

### `customers`
One document per customer from the churn CSV. Tagged with `run_id` for filtering.

Fields: `customer_id`, `region`, `plan_type`, `account_age_months`, `data_usage_mb_this_month`, `data_usage_mb_last_month`, `data_usage_mb_2_months_ago`, `days_since_recharge`, `complaints_last_30_days`, `churn_risk`, `run_id`

### `campaigns`
One document per launched campaign. Written by Action 4.

```json
{
  "campaign_id": "uuid",
  "run_id": "uuid",
  "target_count": 2000,
  "batch_count": 4,
  "sms_per_batch": 500,
  "status": "launched",
  "sms_template": "Hey! We noticed...",
  "scheduled_batches": []
}
```

### `action_logs`
One document per action executed. Includes failures and rollbacks.

```json
{
  "run_id": "uuid",
  "step": 3,
  "action_name": "update_crm",
  "status": "rolled_back",
  "error_message": "Mock CRM API returned HTTP 500",
  "retry_count": 1,
  "timestamp": "..."
}
```

---

## Repository Structure

```
TeleSight/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── requirements.txt
│   ├── .env.example
│   ├── agents/
│   │   └── pipeline.py          # LangGraph pipeline — all 5 nodes + Gemini
│   ├── parsers/
│   │   ├── csv_parser.py        # CSV ingestion + noise filtering
│   │   ├── pdf_parser.py        # PDF text extraction
│   │   ├── json_parser.py       # JSON dashboard parser
│   │   ├── article_parser.py    # URL article scraper
│   │   ├── feed_parser.py       # Live feed + Wikipedia API
│   │   ├── worldbank_parser.py  # World Bank Open Data API
│   │   └── news_parser.py       # NewsAPI.org integration
│   ├── routes/
│   │   ├── upload.py            # Upload + pipeline trigger endpoints
│   │   ├── mock_apis.py         # Self-hosted CRM + Reports APIs
│   │   └── actions.py           # Action execution + logs endpoints
│   └── db/
│       └── __init__.py          # MongoDB Atlas connection
├── frontend/                    # Flutter (Not built yet)
└── data/
    ├── churn_data.csv           # Mock dataset — 5,000 customers
    ├── kpi_dashboard.json       # Mock KPI snapshot
    ├── monthly_report.pdf       # Mock regional performance report
    └── generate_mock_data.py    # Script to regenerate mock data
```

---

## Local Setup

### Prerequisites
- Python 3.10+
- Google Cloud account with Vertex AI API enabled
- MongoDB Atlas account
- NewsAPI.org free API key
- Google Cloud CLI installed and authenticated

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/TeleSight.git
cd TeleSight/backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in `/backend`:

```env
MONGODB_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/telesight
MONGODB_DB_NAME=telesight
GOOGLE_PROJECT_ID=your-gcp-project-id
GOOGLE_LOCATION=us-central1
NEWSAPI_KEY=your-newsapi-key
```

### Google Cloud Authentication

```bash
gcloud auth application-default login
gcloud config set project your-project-id
```

### Generate Mock Data

```bash
cd ../data
python generate_mock_data.py
# Convert monthly_report.txt to PDF via Google Docs
```

### Run the Server

```bash
cd ../backend
uvicorn main:app --reload
# API docs: http://localhost:8000/docs
# Health check: http://localhost:8000/health
```

---

## Testing the Full Pipeline

```bash
# 1. Upload all 5 sources
POST /api/upload
# Returns: { "run_id": "...", "status": "ingested", "data_sources": [...] }

# 2. Run the agent pipeline
POST /api/pipeline/run/{run_id}
# Returns: full pipeline state with all 5 node outputs

# 3. Execute the action chain
POST /api/actions/execute/{run_id}
# Returns: outcome with before/after state

# 4. Check action logs
GET /api/actions/logs/{run_id}
# Returns: 6 log entries (action 3 has 2 — failed + rolled_back)
```

---

## Custom Data Upload

Users can upload their own churn CSV and PDF report instead of using the default API sources.

```bash
POST /api/upload
use_live_apis: false
csv_file: your_churn_data.csv
pdf_file: your_monthly_report.pdf
```

The agent automatically adjusts all reasoning, insights, constraints, and action plan to the new data. CSV must follow the TeleSight schema:

```
customer_id, region, data_usage_mb_this_month,
data_usage_mb_last_month, data_usage_mb_2_months_ago,
days_since_recharge, complaints_last_30_days,
plan_type, account_age_months, churn_risk
```

---

## Assumptions & Limitations

- All churn data is mock-generated. No real Telenor customer data is used.
- CRM failure in Action 3 is deliberately injected for demonstration purposes.
- SMS campaign is simulated via MongoDB writes — no real SMS gateway is connected.
- Manager notification is simulated — no real email or Slack integration.
- Revenue loss projection uses PKR 340 ARPU and 65% churn conversion rate (industry estimates).
- NewsAPI may return no results for Pakistan-specific telecom queries on some days — contradiction detection falls back to PDF-only in that case.
- Article URL parser depends on the target site being publicly accessible.

---

