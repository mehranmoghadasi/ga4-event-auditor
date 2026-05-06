# GA4 Event Auditor 🔍

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

A command-line tool that audits your Google Analytics 4 (GA4) event implementation by comparing live event data from the GA4 Data API against your defined measurement plan. Identifies missing events, parameter mismatches, and naming inconsistencies — saving analysts hours of manual tag auditing.

## The Problem

GA4 implementations break silently. Events get renamed, parameters go missing, and nobody notices until a campaign report looks wrong three months later. Manual auditing means clicking through DebugView and hoping you catch everything.

## The Solution

GA4 Event Auditor connects to the GA4 Data API, pulls your last 30 days of event data, and compares it against a JSON measurement plan you define. It produces a detailed report showing exactly what's firing, what's missing, and what's named incorrectly.

## Features

- 📋 Load measurement plan from JSON (define expected events + parameters)
- 📡 Fetch live event data via GA4 Data API (no sampling)
- ✅ Detect implemented events matching the plan
- ❌ Flag missing events not seen in the last 30 days
- ⚠️ Identify events firing without expected parameters
- 🏷️ Catch naming inconsistencies (e.g., `Add_To_Cart` vs `add_to_cart`)
- 📊 Generate color-coded console report + CSV export
- 🔁 Run as a cron job for continuous implementation health monitoring

## Tech Stack

- Python 3.8+
- Google Analytics Data API (`google-analytics-data`)
- `google-auth` for OAuth2 / Service Account authentication
- `jinja2` for HTML report generation
- `pandas` for data manipulation

## Installation

```bash
git clone https://github.com/mehranmoghadasi/ga4-event-auditor.git
cd ga4-event-auditor
pip install -r requirements.txt
```

### Requirements

```
google-analytics-data==0.18.3
google-auth==2.28.0
pandas==2.2.1
jinja2==3.1.3
```

## Setup

### 1. Create a Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a Service Account with **Viewer** role
3. Download the JSON key file
4. Add the service account email as a **Viewer** in your GA4 property

### 2. Define Your Measurement Plan

Create `measurement_plan.json`:

```json
{
  "property_id": "YOUR_GA4_PROPERTY_ID",
  "events": [
    {
      "name": "purchase",
      "required_parameters": ["transaction_id", "value", "currency", "items"]
    },
    {
      "name": "add_to_cart",
      "required_parameters": ["currency", "value", "items"]
    },
    {
      "name": "generate_lead",
      "required_parameters": ["form_id", "page_location"]
    },
    {
      "name": "begin_checkout",
      "required_parameters": ["currency", "value"]
    }
  ]
}
```

## Usage

```bash
# Basic audit
python audit.py --credentials service-account.json --plan measurement_plan.json --days 30

# Save CSV report
python audit.py --credentials service-account.json --plan measurement_plan.json --output report.csv

# Demo mode (no API needed)
python audit.py --demo
```

## Sample Output

```
GA4 Event Audit Report — May 2026
Property: 123456789 | Audit Period: Last 30 days
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ IMPLEMENTED (2/4 events)
  purchase         — 1,247 occurrences — all parameters present
  add_to_cart      — 3,891 occurrences — all parameters present

❌ MISSING (1/4 events)
  generate_lead    — 0 occurrences in last 30 days

⚠️  PARAMETER ISSUES (1/4 events)
  begin_checkout   — 892 occurrences — missing: currency

🏷️  UNPLANNED EVENTS FIRING (3 events)
  Add_To_Cart      — 44 occurrences  [naming issue: should be add_to_cart]
  checkout_start   — 211 occurrences [not in plan]
  form_submit      — 78 occurrences  [not in plan]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall Health Score: 62/100
```

## License

MIT License — see [LICENSE](LICENSE) for details.
