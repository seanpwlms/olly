from __future__ import annotations

from prefab_ui.components import (
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    ChartSeries,
    Column,
    DataTable,
    H2,
    H3,
    LineChart,
    Row,
    Text,
)
from prefab_ui.actions import SetState

from olly.dashboard_prefab.components import (
    findings_table,
    stat_card,
)


def build_dashboard_page():
    """Build the main dashboard index page."""
    with Column(gap=6) as page:
        # Page title
        H2("Dashboard Overview")

        # Debug: show counts
        Text("Debug: {{ findings_count }} findings, {{ dbt_findings_count }} dbt findings, {{ tables_count }} tables")

        # Note: Table detail page shows data for main.customers (first table in state)
        with Card(css_class="bg-blue-50"):
            with CardHeader():
                CardTitle("Table Details")
                CardDescription("Click to view table detail page")
            with CardContent():
                Button(
                    "View Table Details (main.customers)",
                    variant="outline",
                    on_click=SetState("page", "table_detail"),
                )

        # Stats row - 4 key metrics
        with Row(gap=4, css_class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4"):
            stat_card("stats.error_count", "Errors", variant="error")
            stat_card("stats.warning_count", "Warnings", variant="warning")
            stat_card("stats.tables_monitored", "Tables Monitored", variant="success")
            with Card():
                with CardHeader():
                    CardTitle("Last Check")
                with CardContent():
                    Text("{{ stats.last_check_time or 'Never' }}")

        # Check breakdown section
        with Column(gap=4):
            H3("Check Breakdown")
            with Row(gap=4, css_class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3"):
                # Use actual breakdown from state
                with Card():
                    with CardHeader():
                        CardTitle("Schema")
                    with CardContent():
                        with Row(gap=4):
                            with Column():
                                Text("{{ check_breakdown.schema.errors }}", css_class="text-2xl font-bold text-red-600")
                                Text("Errors", css_class="text-sm text-gray-500")
                            with Column():
                                Text("{{ check_breakdown.schema.warnings }}", css_class="text-2xl font-bold text-yellow-600")
                                Text("Warnings", css_class="text-sm text-gray-500")

                with Card():
                    with CardHeader():
                        CardTitle("Volume")
                    with CardContent():
                        with Row(gap=4):
                            with Column():
                                Text("{{ check_breakdown.volume.errors }}", css_class="text-2xl font-bold text-red-600")
                                Text("Errors", css_class="text-sm text-gray-500")
                            with Column():
                                Text("{{ check_breakdown.volume.warnings }}", css_class="text-2xl font-bold text-yellow-600")
                                Text("Warnings", css_class="text-sm text-gray-500")

                with Card():
                    with CardHeader():
                        CardTitle("Freshness")
                    with CardContent():
                        with Row(gap=4):
                            with Column():
                                Text("{{ check_breakdown.freshness.errors }}", css_class="text-2xl font-bold text-red-600")
                                Text("Errors", css_class="text-sm text-gray-500")
                            with Column():
                                Text("{{ check_breakdown.freshness.warnings }}", css_class="text-2xl font-bold text-yellow-600")
                                Text("Warnings", css_class="text-sm text-gray-500")

        # Findings table
        with Column(gap=4):
            H3("Recent Findings")
            findings_table("findings", filterable=True)

        # DBT results preview
        with Column(gap=4):
            H3("DBT Results")
            Text("{{ stats.dbt_error_count }} errors, {{ stats.dbt_warning_count }} warnings")
            # Show all dbt findings (prefab may not support slice filter)
            DataTable(
                rows="{{ dbt_findings }}",
                columns=[
                    {"header": "Severity", "key": "severity"},
                    {"header": "Type", "key": "resource_type"},
                    {"header": "Node", "key": "unique_id"},
                    {"header": "Status", "key": "status"},
                ],
            )

    return page


def build_tables_page():
    """Build the tables list page."""
    with Column(gap=6) as page:
        H2("Tables")
        Text("{{ tables_count }} tables monitored")

        # Tables list with DataTable (has built-in search and sorting)
        DataTable(
            rows="{{ tables }}",
            columns=[
                {"header": "Schema", "key": "schema"},
                {"header": "Table", "key": "table"},
                {"header": "Type", "key": "type"},
                {"header": "Columns", "key": "columns"},
                {"header": "Row Count", "key": "row_count"},
            ],
            searchable=True,
        )

    return page


def build_table_detail_page():
    """Build the table detail page."""
    with Column(gap=6) as page:
        # Header with table name
        H2("{{ detail_schema }}.{{ detail_table }}")

        # Stats row
        with Row(gap=4, css_class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4"):
            with Card():
                with CardHeader():
                    CardDescription("Type")
                    CardTitle("{{ detail_info.table_type }}")
            with Card():
                with CardHeader():
                    CardDescription("Columns")
                    CardTitle("{{ detail_info.columns.length }}")
            with Card():
                with CardHeader():
                    CardDescription("Row Count")
                    CardTitle("{{ detail_volume.current }}")
            with Card():
                with CardHeader():
                    CardDescription("Change %")
                    CardTitle("{{ detail_volume.delta_pct }}")

        # Volume trend chart
        with Card():
            with CardHeader():
                CardTitle("Volume Trend")
            with CardContent():
                LineChart(
                    data="{{ detail_timeseries }}",
                    x_axis="snapshot",
                    series=[ChartSeries(data_key="row_count", label="Row Count")],
                    height=250,
                    show_dots=True,
                    css_class="w-full",
                )

        # Volume stats
        with Card():
            with CardHeader():
                CardTitle("Volume Statistics")
            with CardContent():
                with Row(gap=4):
                    with Column():
                        Text("Min: {{ detail_volume.minimum }}")
                        Text("Max: {{ detail_volume.maximum }}")
                    with Column():
                        Text("Avg: {{ detail_volume.average }}")
                        Text("Snapshots: {{ detail_volume.snapshot_count }}")

        # Findings for this table
        with Column(gap=4):
            H3("Findings")
            DataTable(
                rows="{{ detail_findings }}",
                columns=[
                    {"header": "Check", "key": "check_type"},
                    {"header": "Severity", "key": "severity"},
                    {"header": "Description", "key": "description"},
                ],
                searchable=False,
            )

        # Schema
        with Column(gap=4):
            H3("Current Schema")
            DataTable(
                rows="{{ detail_info.columns }}",
                columns=[
                    {"header": "Column", "key": "name"},
                    {"header": "Type", "key": "dtype"},
                    {"header": "Nullable", "key": "nullable"},
                ],
            )

    return page


def build_usage_page():
    """Build the usage/cost page."""
    with Column(gap=6) as page:
        H2("Usage & Cost")

        # Stats row
        with Row(gap=4, css_class="grid grid-cols-1 md:grid-cols-3"):
            stat_card("usage_stats.unused_count", "Unused Tables", variant="error")
            stat_card("usage_stats.stale_count", "Stale Tables", variant="warning")
            stat_card("usage_stats.total_cost_usd", "Total Cost (USD)", variant="success")

        # Usage findings
        with Column(gap=4):
            H3("Usage Findings")
            findings_table("usage_findings", filterable=False)

    return page


def build_dbt_page():
    """Build the dbt results page."""
    with Column(gap=6) as page:
        H2("DBT Results")

        # Stats row
        with Row(gap=4, css_class="grid grid-cols-1 md:grid-cols-2"):
            stat_card("stats.dbt_error_count", "Errors", variant="error")
            stat_card("stats.dbt_warning_count", "Warnings", variant="warning")

        # DBT findings table
        with Column(gap=4):
            H3("DBT Test Results")
            DataTable(
                rows="{{ dbt_findings }}",
                columns=[
                    {"header": "Severity", "key": "severity"},
                    {"header": "Type", "key": "resource_type"},
                    {"header": "Node", "key": "unique_id"},
                    {"header": "Status", "key": "status"},
                    {"header": "Execution Time", "key": "execution_time"},
                    {"header": "Description", "key": "description"},
                ],
                searchable=True,
                filterable=True,
            )

    return page
