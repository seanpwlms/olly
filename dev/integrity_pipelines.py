"""Integrity sync definitions for the dev environment."""

from olly.models import IntegrityMethod, Sync, WindowOp, WindowSpec

syncs = [
    # Passing: payments have identical rows in source and target
    Sync(
        name="payments_sync",
        source="source",
        target="target",
        source_table="main.payments",
        target_table="main.payments",
        method=IntegrityMethod.COUNT,
        key=None,
        hash_columns=None,
        watermark="processed_at",
        window=WindowSpec(
            op=WindowOp.BETWEEN,
            duration=None,
            start="2026-01-15 00:00:00",
            end="2026-01-15 23:59:59",
            value=None,
        ),
        where=None,
        tolerance_delta=None,
        tolerance_ratio=None,
        tolerance_mode=None,
        severity="error",
    ),
    # Failing: target shipments is missing 2 rows
    Sync(
        name="shipments_sync",
        source="source",
        target="target",
        source_table="main.shipments",
        target_table="main.shipments",
        method=IntegrityMethod.COUNT,
        key=None,
        hash_columns=None,
        watermark="shipped_at",
        window=WindowSpec(
            op=WindowOp.BETWEEN,
            duration=None,
            start="2026-01-15 00:00:00",
            end="2026-01-15 23:59:59",
            value=None,
        ),
        where=None,
        tolerance_delta=None,
        tolerance_ratio=None,
        tolerance_mode=None,
        severity="error",
    ),
]
