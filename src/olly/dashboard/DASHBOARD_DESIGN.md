# Olly Dashboard Design Document

## Overview

The Olly dashboard provides a web-based interface for monitoring data quality across all configured warehouse connections. It surfaces findings, trends, and configuration details from the snapshot-and-diff workflow.

## Data Sources

- **Primary**: `~/.olly/<project-hash>/findings.json` — current check results
- **Historical**: `~/.olly/<project-hash>/state.db` — snapshot history, volume records, timestamps
- **Configuration**: `olly.toml` in project root — settings, thresholds, overrides

## Architecture

- **Framework**: FastAPI + Jinja2 templates
- **Styling**: Simple, responsive design (minimal dependencies)
- **Update Model**: Static reads from files/DB (no live connections to warehouses)
- **Refresh**: User manually re-runs `olly check` to update findings

---

## Page Structure

### 1. **Home / Overview** (`/`)

**Purpose**: At-a-glance health status across all connections

**Layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ Olly Dashboard                                   Last Check: │
│                                                   2 hours ago │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Health Summary                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ 🔴 3 Errors  │  │ ⚠️  8 Warnings│  │ ✅ 45 Tables │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                               │
│  Findings by Connection                                       │
│  ┌────────────────────────────────────────────────────┐      │
│  │ primary        2 errors    5 warnings   20 tables  │      │
│  │ analytics      1 error     3 warnings   25 tables  │      │
│  └────────────────────────────────────────────────────┘      │
│                                                               │
│  Recent Critical Issues                                       │
│  ┌────────────────────────────────────────────────────┐      │
│  │ [schema/error]   main.customers                    │      │
│  │   Column removed: main.customers.email             │      │
│  │                                                     │      │
│  │ [integrity/error] orders_sync                      │      │
│  │   Row count mismatch: source 1000, target 998     │      │
│  └────────────────────────────────────────────────────┘      │
│                                                               │
│  Findings by Check Type                                       │
│  ┌────────────────────────────────────────────────────┐      │
│  │ Schema       2 errors    1 warning                 │      │
│  │ Volume       0 errors    3 warnings                │      │
│  │ Freshness    0 errors    2 warnings                │      │
│  │ Integrity    1 error     0 warnings                │      │
│  │ Contracts    0 errors    2 warnings                │      │
│  │ dbt          0 errors    0 warnings                │      │
│  │ Usage        0 errors    0 warnings                │      │
│  │ Cost         0 errors    0 warnings                │      │
│  └────────────────────────────────────────────────────┘      │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Key Metrics**:
- Total error/warning counts
- Findings grouped by connection
- Findings grouped by check type
- Top 5 most recent/critical findings
- Timestamp of last `olly check` run

**Actions**:
- Click connection → filter to connection on Findings page
- Click check type → filter to check type on Findings page
- Click table → go to table detail page

---

### 2. **Findings** (`/findings`)

**Purpose**: Comprehensive, filterable list of all current findings

**Layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ Findings                                                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Filters:                                                     │
│  [Connection ▾] [Check Type ▾] [Severity ▾] [Search table]   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Check    │ Severity │ Table          │ Description   │   │
│  ├──────────┼──────────┼────────────────┼───────────────┤   │
│  │ schema   │ 🔴 error │ main.customers │ Column removed│   │
│  │          │          │                │ main.customer…│   │
│  │──────────┼──────────┼────────────────┼───────────────┤   │
│  │ schema   │ ⚠️ warn  │ main.orders    │ New column:   │   │
│  │          │          │                │ main.orders.…│   │
│  │──────────┼──────────┼────────────────┼───────────────┤   │
│  │ freshness│ ⚠️ warn  │ main.payments  │ Stale data: … │   │
│  │──────────┼──────────┼────────────────┼───────────────┤   │
│  │ volume   │ ⚠️ warn  │ main.orders    │ Row count ano…│   │
│  │          │          │                │ z-score: +3.20│   │
│  └──────────┴──────────┴────────────────┴───────────────┘   │
│                                                               │
│  Showing 4 of 11 findings                        [Export JSON]│
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Interactive table with sortable columns
- Multi-select filters (connection, check type, severity)
- Text search for table names
- Export to JSON button (download current findings.json)
- Click row → expand for full details + link to table page

**Data Fields**:
- Connection name
- Check type
- Severity (error/warning)
- Table name (schema.table)
- Description
- Timestamp (when finding was detected)

---

### 3. **Tables** (`/tables`)

**Purpose**: Table-centric view with historical trends and current status

**Layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ Tables                                                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  [Connection ▾] [Schema ▾] [Search table]                    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Table           │ Rows      │ Status    │ Last Check│   │
│  ├─────────────────┼───────────┼───────────┼───────────┤   │
│  │ main.customers  │ 1,234     │ 🔴 1 error│ 2h ago    │   │
│  │ main.orders     │ 12,345    │ ⚠️ 2 warn │ 2h ago    │   │
│  │ main.payments   │ 45,678    │ ⚠️ 1 warn │ 2h ago    │   │
│  │ main.products   │ 567       │ ✅ OK     │ 2h ago    │   │
│  └─────────────────┴───────────┴───────────┴───────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- List all monitored tables across connections
- Current row count
- Status indicator (errors/warnings/OK)
- Last check timestamp
- Click table → go to table detail page

---

### 4. **Table Detail** (`/tables/<connection>/<schema>/<table>`)

**Purpose**: Deep dive into a single table's health, history, and configuration

**Layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ main.orders                                  Connection: primary│
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Current Status                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Rows: 12,345    Status: ⚠️ 2 warnings                │   │
│  │ Last Updated: 2 hours ago                            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Active Findings                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ [schema/warning] New column: main.orders.status      │   │
│  │ [volume/warning] Row count anomaly (z-score: +3.20)  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Volume History (last 30 snapshots)                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        ╱╲                                            │   │
│  │       ╱  ╲     ╱╲                                    │   │
│  │   ───╱    ╲───╱  ╲───                               │   │
│  │                                                      │   │
│  │  ← 30 days ago              Today →                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Schema                                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Column       │ Type    │ Nullable │ Status          │   │
│  ├──────────────┼─────────┼──────────┼─────────────────┤   │
│  │ id           │ int64   │ No       │ ✅              │   │
│  │ amount       │ float64 │ No       │ ✅              │   │
│  │ created_at   │ timestamp│ No      │ ✅              │   │
│  │ status       │ string  │ Yes      │ 🆕 New column   │   │
│  └──────────────┴─────────┴──────────┴─────────────────┘   │
│                                                               │
│  Configuration                                                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Freshness Threshold: 168.0 hours (override)          │   │
│  │ Volume Z-Score Threshold: 5.0 (override)             │   │
│  │ Freshness Column: updated_at (override)              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Contract (if defined)                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Class: Orders                                        │   │
│  │ Strict: True                                         │   │
│  │ Status: ✅ Passing                                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Current metrics (row count, last update)
- All findings for this table
- Volume trend chart (simple line chart or sparkline)
- Current schema with change indicators
- Resolved configuration (from config-explain logic)
- Contract status (if applicable)
- Links to related tables (integrity syncs)

---

### 5. **Cost** (`/cost`) — BigQuery only

**Purpose**: Cost monitoring and spike detection

**Layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ Query Cost Analysis                      Connection: warehouse│
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Current Period (last 30 days)                                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Total Cost: $1,234.56                                │   │
│  │ Status: ⚠️ Spike detected (z-score: +3.5)            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Cost History                                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ $                                                    │   │
│  │  1400│                                          ╱    │   │
│  │  1200│                                         ╱     │   │
│  │  1000│        ╱╲                          ╱╲ ╱      │   │
│  │   800│       ╱  ╲    ╱╲                 ╱  ╲╱       │   │
│  │   600│   ───╱    ╲──╱  ╲───────────────╱           │   │
│  │      └──────────────────────────────────────        │   │
│  │       ← 6 months ago          Today →               │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Top Tables by Cost                                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Table              │ Cost      │ Queries │ Avg Cost  │   │
│  ├────────────────────┼───────────┼─────────┼───────────┤   │
│  │ analytics.events   │ $456.78   │ 1,234   │ $0.37     │   │
│  │ analytics.users    │ $234.56   │ 567     │ $0.41     │   │
│  │ analytics.sessions │ $123.45   │ 890     │ $0.14     │   │
│  └────────────────────┴───────────┴─────────┴───────────┘   │
│                                                               │
│  Top Users by Cost                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ User               │ Cost      │ Queries │ Avg Cost  │   │
│  ├────────────────────┼───────────┼─────────┼───────────┤   │
│  │ analytics-pipeline │ $567.89   │ 2,345   │ $0.24     │   │
│  │ data-team@co.com   │ $345.67   │ 456     │ $0.76     │   │
│  │ dashboard-service  │ $234.56   │ 3,456   │ $0.07     │   │
│  └────────────────────┴───────────┴─────────┴───────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Current period total cost
- Spike detection status
- Historical cost trend chart
- Top tables by spend (with query counts)
- Top users by spend (with query counts)
- Only shown if BigQuery connection + cost monitoring enabled

---

### 6. **History** (`/history`)

**Purpose**: Historical view of findings over time

**Layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ Check History                                                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Error/Warning Trend (last 30 snapshots)                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Count                                                │   │
│  │   10│                                                │   │
│  │    8│  Warnings ·············                       │   │
│  │    6│            ·     ·   ·                        │   │
│  │    4│  Errors   ──╲   ╱╲ ╱╲                        │   │
│  │    2│             ╲─╱  ╲╱ ╲──                      │   │
│  │    0└──────────────────────────────────            │   │
│  │      ← 30 days ago        Today →                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Recent Snapshots                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Timestamp          │ Errors │ Warnings │ Tables     │   │
│  ├────────────────────┼────────┼──────────┼────────────┤   │
│  │ 2024-01-15 14:30   │ 3      │ 8        │ 45         │   │
│  │ 2024-01-15 12:00   │ 2      │ 7        │ 45         │   │
│  │ 2024-01-15 10:00   │ 2      │ 6        │ 45         │   │
│  │ 2024-01-15 08:00   │ 1      │ 5        │ 44         │   │
│  └────────────────────┴────────┴──────────┴────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Trend chart showing error/warning counts over snapshots
- Timeline of snapshot runs
- Click snapshot → view findings from that point in time
- Historical comparison (compare two snapshots)

---

### 7. **Configuration** (`/config`)

**Purpose**: Show resolved configuration (like `olly config-explain`)

**Layout**:

```
┌─────────────────────────────────────────────────────────────┐
│ Configuration                                                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Global Settings                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Freshness Threshold: 24.0 hours                      │   │
│  │ Volume Z-Score Threshold: 3.0                        │   │
│  │ History Depth: 30 snapshots                          │   │
│  │ Min History for Anomaly: 5 snapshots                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Connections                                                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ primary (duckdb)                                     │   │
│  │   Path: warehouse.duckdb                             │   │
│  │   Schemas: main                                      │   │
│  │   Tables: 20                                         │   │
│  │                                                      │   │
│  │ analytics (postgres)                                 │   │
│  │   URL: postgresql://...                             │   │
│  │   Schemas: public                                    │   │
│  │   Tables: 25                                         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Table Overrides                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ main.orders                                          │   │
│  │   freshness_threshold_hours: 168                     │   │
│  │   volume_zscore_threshold: 5.0                       │   │
│  │                                                      │   │
│  │ main.*                                               │   │
│  │   freshness_column: updated_at                       │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Integrity Syncs                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ orders_count                                         │   │
│  │   Source: warehouse → main.orders                    │   │
│  │   Target: replica → public.orders                    │   │
│  │   Method: COUNT                                      │   │
│  │   Watermark: updated_at                              │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  Contracts                                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Orders (main.orders)                                 │   │
│  │ Customers (main.customers)                           │   │
│  │ Payments (main.payments)                             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Features**:
- Display global settings
- List all connections with details
- Show table-level overrides
- List integrity syncs
- List contracts
- Read-only view (no editing in dashboard)

---

## Navigation

**Top Navigation Bar**:
```
┌─────────────────────────────────────────────────────────────┐
│ 🔍 Olly  │ Overview │ Findings │ Tables │ Cost │ History │ Config │
└─────────────────────────────────────────────────────────────┘
```

**Sticky Status Banner** (if errors present):
```
┌─────────────────────────────────────────────────────────────┐
│ 🔴 3 errors detected • Last check: 2 hours ago    [Run Check]│
└─────────────────────────────────────────────────────────────┘
```

---

## Visual Design Principles

1. **Status Colors**:
   - 🔴 Red: Errors
   - ⚠️ Yellow: Warnings
   - ✅ Green: OK
   - 🔵 Blue: Info/Neutral

2. **Typography**:
   - Monospace for table/column names, database identifiers
   - Sans-serif for UI text
   - Clear hierarchy (page title → section → content)

3. **Tables**:
   - Sortable columns
   - Hover states
   - Clickable rows
   - Responsive (collapse on mobile)

4. **Charts**:
   - Simple line charts for trends (can use minimal JS library like Chart.js or plain SVG)
   - Sparklines for inline trends
   - Consistent time axis

5. **Responsive**:
   - Mobile-friendly navigation (hamburger menu)
   - Stacked layout on small screens
   - Touch-friendly tap targets

---

## Implementation Notes

### Data Loading

**Backend (FastAPI)**:
```python
@app.get("/")
def home():
    findings = load_findings()  # from findings.json
    state_db = StateDB(...)
    snapshots = state_db.get_recent_snapshots(limit=30)
    return render_template("home.html", findings=findings, snapshots=snapshots)
```

**State DB Queries**:
- `get_recent_snapshots()` — last N snapshots with timestamps
- `get_volume_history(table)` — row counts over time
- `get_error_warning_trend()` — aggregate errors/warnings per snapshot
- `get_all_tables()` — current table list with row counts

**Configuration**:
- Load `olly.toml` and resolve overrides using existing `config.py` logic
- Reuse `config-explain` logic for table-level config display

### Refresh Mechanism

- Dashboard reads static files (no live warehouse queries)
- User runs `olly check` via CLI to update findings
- Optional: Add "Refresh" button that triggers `olly check` via subprocess
- Show last check timestamp prominently
- Optional: Auto-refresh page every N seconds (check if findings.json modified)

### URL Structure

- `/` — Home
- `/findings` — All findings
- `/findings?connection=primary&check=schema&severity=error` — Filtered findings
- `/tables` — Table list
- `/tables/<connection>/<schema>/<table>` — Table detail
- `/cost` — Cost analysis (BigQuery only)
- `/history` — Historical trends
- `/config` — Configuration view
- `/api/findings.json` — Raw JSON export

### Optional Features (Future)

- **Snapshot Comparison**: Compare two snapshots side-by-side
- **Alerts Configuration**: Set up notifications (email, Slack) via UI
- **Manual Refresh**: Button to trigger `olly check` from dashboard
- **Dark Mode**: Toggle light/dark theme
- **Export Reports**: PDF/CSV export of findings
- **Table Search**: Global search for tables across connections
- **Check Schedule**: Show when next check is scheduled (if using cron)

---

## Example User Flows

### Flow 1: Daily Check-In
1. User opens dashboard → lands on **Overview**
2. Sees "3 errors" in health summary
3. Clicks "3 Errors" → goes to **Findings** page filtered to errors
4. Reviews error details, clicks on problematic table
5. Lands on **Table Detail** page, sees schema change history
6. Notes the issue, fixes in warehouse, re-runs `olly check`
7. Refreshes dashboard → errors cleared

### Flow 2: Cost Spike Investigation
1. User receives alert about cost spike
2. Opens **Cost** page
3. Sees spike in chart, identifies period
4. Reviews "Top Tables by Cost" → finds culprit table
5. Clicks table → goes to **Table Detail**
6. Reviews query patterns, optimizes queries
7. Monitors **Cost** page over next few days

### Flow 3: Table Health Deep Dive
1. User wants to understand `main.orders` table
2. Opens **Tables** page, searches "orders"
3. Clicks `main.orders` → **Table Detail**
4. Reviews volume history chart → sees anomaly
5. Checks **Active Findings** → row count spike warning
6. Reviews **Configuration** → confirms z-score threshold
7. Determines spike is expected (Black Friday sale)
8. Adjusts threshold in `olly.toml` if needed

---

## Technical Requirements

- **Python**: FastAPI, Jinja2, SQLite3 (built-in)
- **Frontend**: Minimal JS (optional Chart.js for charts)
- **Styling**: Tailwind CSS or simple custom CSS
- **State**: Read-only access to state.db and findings.json
- **Performance**: Dashboard should load in <1s for typical dataset (100s of tables)

---

## Success Metrics

1. **Clarity**: User can identify and prioritize issues within 10 seconds
2. **Actionability**: Each finding links to relevant context (table detail, config)
3. **Historical Context**: Trends show whether issues are improving or worsening
4. **Coverage**: All check types and data from CLI are accessible in UI
5. **Performance**: Fast page loads even with large finding sets (1000+ tables)
