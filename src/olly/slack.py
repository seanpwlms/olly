from __future__ import annotations

import json
import logging
import urllib.request
from urllib.error import URLError

from olly.config import SlackConfig
from olly.models import DbtFinding, Finding

logger = logging.getLogger(__name__)

_MAX_FINDINGS = 10


def build_slack_payload(
    findings: list[Finding],
    dbt_findings: list[DbtFinding],
) -> dict:
    """Build a Slack Block Kit payload summarising the given findings.

    Args:
        findings: Warehouse findings to include.
        dbt_findings: dbt findings to include.

    Returns:
        A dict suitable for JSON-encoding and POSTing to a Slack webhook.
    """
    error_count = sum(1 for f in findings if f.severity == "error")
    error_count += sum(1 for f in dbt_findings if f.severity == "error")
    warn_count = sum(1 for f in findings if f.severity == "warning")
    warn_count += sum(1 for f in dbt_findings if f.severity == "warning")

    parts = []
    if error_count:
        parts.append(f"{error_count} error(s)")
    if warn_count:
        parts.append(f"{warn_count} warning(s)")
    summary = ", ".join(parts)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":rotating_light: Olly: {summary}",
                "emoji": True,
            },
        }
    ]

    all_findings: list[Finding | DbtFinding] = [*findings, *dbt_findings]
    shown = all_findings[:_MAX_FINDINGS]
    remaining = len(all_findings) - len(shown)

    for f in shown:
        if isinstance(f, Finding):
            table = f"{f.schema_name}.{f.table_name}"
            check = f.check_type
            desc = f.description
        else:
            table = f.unique_id
            check = f.resource_type
            desc = f.description
        severity_icon = ":red_circle:" if f.severity == "error" else ":warning:"
        text = f"{severity_icon} *{table}* [{check}] {desc}"
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": text}}
        )

    if remaining > 0:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"_...and {remaining} more_",
                },
            }
        )

    return {"blocks": blocks}


def send_slack_alert(
    config: SlackConfig,
    findings: list[Finding],
    dbt_findings: list[DbtFinding],
) -> None:
    """Post qualifying findings to the configured Slack webhook.

    Filters findings by ``config.on_error`` / ``config.on_warning`` before
    sending. No-op when unconfigured or when no qualifying findings exist.
    Errors from the HTTP call are logged as warnings and never re-raised.

    Args:
        config: Slack alerting configuration.
        findings: Warehouse findings from the check run.
        dbt_findings: dbt findings from the check run.
    """
    if not config.webhook_url:
        return

    qualifying = [
        f for f in findings
        if (f.severity == "error" and config.on_error)
        or (f.severity == "warning" and config.on_warning)
    ]
    qualifying_dbt = [
        f for f in dbt_findings
        if (f.severity == "error" and config.on_error)
        or (f.severity == "warning" and config.on_warning)
    ]

    if not qualifying and not qualifying_dbt:
        return

    payload = build_slack_payload(qualifying, qualifying_dbt)
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        config.webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            if status != 200:
                logger.warning("Slack webhook returned status %s", status)
    except URLError as exc:
        logger.warning("Failed to send Slack alert: %s", exc)
