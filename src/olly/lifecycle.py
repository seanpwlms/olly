"""Finding identity and lifecycle across check runs.

Every finding gets a ``fingerprint`` that stays the same from run to run
while the underlying issue persists. Comparing fingerprints against the
previous run of the same check classifies each finding as ``new``,
``escalated`` (severity went up), or ``ongoing``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from olly.models import Finding, FindingStatus

# ``details`` keys that distinguish separate issues on the same table.
# Measured values (counts, z-scores, ages) are deliberately excluded so the
# fingerprint survives them changing between runs.
IDENTITY_KEYS: dict[str, tuple[str, ...]] = {
    "schema": ("change", "column"),
    "contracts": ("issue", "column"),
    "volume": ("direction",),
    "freshness": ("reason",),
    "integrity": ("pipeline",),
}

_SEVERITY_RANK = {"warning": 1, "error": 2}


@dataclass
class PriorFinding:
    """A finding from the previous run of the same check."""

    id: int
    severity: str


def fingerprint(finding: Finding) -> str:
    """Return a stable identifier for the issue a finding describes."""
    keys = IDENTITY_KEYS.get(finding.check_type, ())
    parts = [
        finding.connection_name,
        finding.check_type,
        finding.schema_name,
        finding.table_name,
        *(finding.details.get(k) for k in keys),
    ]
    encoded = json.dumps(parts, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def apply_lifecycle(
    findings: list[Finding], previous: dict[str, PriorFinding]
) -> None:
    """Set ``fingerprint`` and ``status`` on each finding in place.

    Args:
        findings: Findings from the current run.
        previous: Findings from the previous run of each check that ran,
            keyed by fingerprint.
    """
    for f in findings:
        f.fingerprint = fingerprint(f)
        prior = previous.get(f.fingerprint)
        if prior is None:
            f.status = FindingStatus.NEW.value
        elif _SEVERITY_RANK.get(f.severity, 0) > _SEVERITY_RANK.get(prior.severity, 0):
            f.status = FindingStatus.ESCALATED.value
        else:
            f.status = FindingStatus.ONGOING.value


def needs_attention(finding: Finding) -> bool:
    """Return True for findings that are new or have escalated."""
    return finding.status != FindingStatus.ONGOING.value
