from __future__ import annotations

from olly.models import Finding


def severity_breakdown_chart(findings: list[Finding]) -> dict:
    """Vega-Lite spec for a grouped bar chart of check_type x severity."""
    counts: dict[tuple[str, str], int] = {}
    for f in findings:
        key = (f.check_type, f.severity)
        counts[key] = counts.get(key, 0) + 1

    data = [
        {"check_type": ct, "severity": sev, "count": cnt}
        for (ct, sev), cnt in sorted(counts.items())
    ]

    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": "container",
        "height": 280,
        "data": {"values": data},
        "mark": {"type": "bar", "tooltip": True},
        "encoding": {
            "x": {"field": "check_type", "type": "nominal", "axis": {"title": None}},
            "y": {
                "field": "count",
                "type": "quantitative",
                "axis": {"title": None},
                "stack": True,
            },
            "color": {
                "field": "severity",
                "type": "nominal",
                "legend": None,
                "scale": {
                    "domain": ["error", "warning"],
                    "range": ["#e74c3c", "#f39c12"],
                },
            },
            "tooltip": [
                {"field": "check_type", "title": "Check"},
                {"field": "severity", "title": "Severity"},
                {"field": "count", "title": "Count"},
            ],
        },
    }


def cost_by_table_chart(top_tables: list[dict]) -> dict:
    """Vega-Lite spec for a horizontal bar chart of cost by table."""
    data = [
        {"table": f"{t['schema']}.{t['table']}", "cost_usd": t["cost_usd"]}
        for t in top_tables
    ]
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": "container",
        "height": max(len(data) * 28, 120),
        "data": {"values": data},
        "mark": {"type": "bar", "tooltip": True, "color": "#0984e3"},
        "encoding": {
            "y": {
                "field": "table",
                "type": "nominal",
                "sort": "-x",
                "axis": {"title": None},
            },
            "x": {
                "field": "cost_usd",
                "type": "quantitative",
                "axis": {"title": "Cost (USD)", "format": "$.2f"},
            },
            "tooltip": [
                {"field": "table", "title": "Table"},
                {"field": "cost_usd", "title": "Cost (USD)", "format": "$.2f"},
            ],
        },
    }


def volume_trend_chart(timeseries: list[dict]) -> dict:
    """Vega-Lite spec for a line chart of row counts over time."""
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": "container",
        "height": 250,
        "data": {"values": timeseries},
        "mark": {"type": "line", "point": True, "tooltip": True},
        "encoding": {
            "x": {"field": "snapshot", "type": "temporal", "title": "Snapshot Time"},
            "y": {"field": "row_count", "type": "quantitative", "title": "Row Count"},
            "tooltip": [
                {"field": "snapshot", "type": "temporal", "title": "Snapshot"},
                {"field": "row_count", "type": "quantitative", "title": "Row Count"},
            ],
        },
    }
