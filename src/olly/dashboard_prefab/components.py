from __future__ import annotations

from prefab_ui.actions import SetState
from prefab_ui.components import (
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Column,
    DataTable,
    Row,
    Text,
)


def stat_card(value_key: str, label: str, variant: str | None = None):
    """Create a statistics card displaying a value and label."""
    css_class = "border-l-4"
    if variant == "error":
        css_class += " border-l-red-500"
    elif variant == "warning":
        css_class += " border-l-yellow-500"
    elif variant == "success":
        css_class += " border-l-green-500"

    with Card(css_class=css_class):
        with CardHeader():
            CardDescription(label)
            CardTitle(f"{{{{ {value_key} }}}}", css_class="text-3xl")


def severity_badge(severity_value: str):
    """Create a badge with appropriate variant for severity."""
    # Conditional badge rendering based on severity
    # In prefab-ui, we can use template logic
    with Column(css_class="inline-flex"):
        Badge(
            f"{{{{ {severity_value} }}}}",
            variant="destructive if {{ {severity_value} }} == 'error' else 'warning'",
        )


def table_link(schema_key: str, table_key: str, display_text: str | None = None):
    """Create a clickable link that navigates to table detail page."""
    text = display_text or f"{{{{ {schema_key} }}}}.{{{{ {table_key} }}}}"
    Button(
        text,
        variant="link",
        css_class="p-0 h-auto font-normal",
        on_click=[
            SetState("detail_schema", f"{{{{ {schema_key} }}}}"),
            SetState("detail_table", f"{{{{ {table_key} }}}}"),
            SetState("page", "table_detail"),
        ],
    )


def findings_table(findings_key: str = "findings", filterable: bool = False):
    """Create a findings table with optional filtering."""
    columns = [
        {"header": "Check", "key": "check_type"},
        {"header": "Severity", "key": "severity"},
        {"header": "Schema", "key": "schema_name"},
        {"header": "Table", "key": "table_name"},
        {"header": "Description", "key": "description"},
    ]

    # Note: DataTable in prefab-ui supports automatic filtering and sorting
    DataTable(
        rows=f"{{{{ {findings_key} }}}}",
        columns=columns,
        searchable=filterable,
    )


def check_breakdown_card(
    check_type: str, error_count: int, warning_count: int
):
    """Create a card showing error/warning counts for a specific check type."""
    with Card():
        with CardHeader():
            CardTitle(check_type.replace("_", " ").title())
        with CardContent():
            with Row(gap=4):
                with Column():
                    Text(str(error_count), css_class="text-2xl font-bold text-red-600")
                    Text("Errors", css_class="text-sm text-gray-500")
                with Column():
                    Text(str(warning_count), css_class="text-2xl font-bold text-yellow-600")
                    Text("Warnings", css_class="text-sm text-gray-500")
