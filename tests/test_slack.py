"""Tests for Slack alerting (slack.py)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from olly.config import SlackConfig
from olly.models import DbtFinding
from olly.slack import _MAX_FINDINGS, build_slack_payload, send_slack_alert
from conftest import make_finding


def _finding(severity="error", check_type="schema", table="orders"):
    """Wrapper for backward compatibility with existing tests."""
    return make_finding(check_type=check_type, severity=severity, table_name=table)


def _dbt_finding(severity="error"):
    return DbtFinding(
        resource_type="model",
        unique_id="model.project.orders",
        status="fail",
        severity=severity,
        execution_time=1.0,
        description="dbt failure",
    )


# --- build_slack_payload ---


def test_payload_header_with_errors():
    payload = build_slack_payload([_finding("error")], [])
    header_text = payload["blocks"][0]["text"]["text"]
    assert "1 error(s)" in header_text


def test_payload_header_with_warnings():
    payload = build_slack_payload([_finding("warning")], [])
    header_text = payload["blocks"][0]["text"]["text"]
    assert "1 warning(s)" in header_text


def test_payload_header_mixed():
    payload = build_slack_payload([_finding("error"), _finding("warning")], [])
    header_text = payload["blocks"][0]["text"]["text"]
    assert "1 error(s)" in header_text
    assert "1 warning(s)" in header_text


def test_payload_includes_dbt_findings():
    payload = build_slack_payload([], [_dbt_finding("error")])
    header_text = payload["blocks"][0]["text"]["text"]
    assert "1 error(s)" in header_text
    # One finding section + header
    assert len(payload["blocks"]) == 2


def test_payload_finding_section_content():
    finding = _finding("error", check_type="volume", table="events")
    payload = build_slack_payload([finding], [])
    section_text = payload["blocks"][1]["text"]["text"]
    assert "main.events" in section_text
    assert "volume" in section_text
    assert "Test finding" in section_text


def test_payload_dbt_finding_section_content():
    dbt = _dbt_finding("error")
    payload = build_slack_payload([], [dbt])
    section_text = payload["blocks"][1]["text"]["text"]
    assert "model.project.orders" in section_text
    assert "model" in section_text


def test_payload_truncates_at_max():
    findings = [_finding(table=f"t{i}") for i in range(_MAX_FINDINGS + 5)]
    payload = build_slack_payload(findings, [])
    # header + MAX_FINDINGS sections + 1 footer
    assert len(payload["blocks"]) == _MAX_FINDINGS + 2
    last_text = payload["blocks"][-1]["text"]["text"]
    assert "5 more" in last_text


def test_payload_no_truncation_footer_when_fits():
    findings = [_finding(table=f"t{i}") for i in range(3)]
    payload = build_slack_payload(findings, [])
    # header + 3 sections, no footer
    assert len(payload["blocks"]) == 4
    last_text = payload["blocks"][-1]["text"]["text"]
    assert "more" not in last_text


def test_payload_error_icon():
    payload = build_slack_payload([_finding("error")], [])
    section_text = payload["blocks"][1]["text"]["text"]
    assert ":red_circle:" in section_text


def test_payload_warning_icon():
    payload = build_slack_payload([_finding("warning")], [])
    section_text = payload["blocks"][1]["text"]["text"]
    assert ":warning:" in section_text


# --- send_slack_alert ---


def test_send_noop_when_no_webhook():
    config = SlackConfig(webhook_url=None)
    with patch("urllib.request.urlopen") as mock_open:
        send_slack_alert(config, [_finding()], [])
        mock_open.assert_not_called()


def test_send_noop_when_no_qualifying_findings():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test", on_error=False, on_warning=False)
    with patch("urllib.request.urlopen") as mock_open:
        send_slack_alert(config, [_finding("error")], [])
        mock_open.assert_not_called()


def test_send_noop_when_only_warnings_and_on_warning_false():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test", on_error=True, on_warning=False)
    with patch("urllib.request.urlopen") as mock_open:
        send_slack_alert(config, [_finding("warning")], [])
        mock_open.assert_not_called()


def test_send_posts_on_error():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test", on_error=True)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_slack_alert(config, [_finding("error")], [])
        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        assert req.get_method() == "POST"
        body = json.loads(req.data)
        assert "blocks" in body


def test_send_posts_on_warning_when_enabled():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test", on_warning=True, on_error=False)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_slack_alert(config, [_finding("warning")], [])
        mock_open.assert_called_once()


def test_send_filters_by_severity():
    """Only errors are sent when on_warning is False."""
    config = SlackConfig(webhook_url="https://hooks.slack.com/test", on_error=True, on_warning=False)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_slack_alert(config, [_finding("error"), _finding("warning")], [])
        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        body = json.loads(req.data)
        # Only the error appears — header says 1 error
        header_text = body["blocks"][0]["text"]["text"]
        assert "1 error(s)" in header_text
        assert "warning" not in header_text


def test_send_swallows_url_error(caplog):
    config = SlackConfig(webhook_url="https://hooks.slack.com/test")
    with patch("urllib.request.urlopen", side_effect=URLError("network error")):
        import logging
        with caplog.at_level(logging.WARNING, logger="olly.slack"):
            send_slack_alert(config, [_finding()], [])
    assert "Failed to send Slack alert" in caplog.text


def test_send_logs_non_200_status(caplog):
    config = SlackConfig(webhook_url="https://hooks.slack.com/test")
    mock_resp = MagicMock()
    mock_resp.status = 400
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    import logging
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with caplog.at_level(logging.WARNING, logger="olly.slack"):
            send_slack_alert(config, [_finding()], [])
    assert "400" in caplog.text


def test_send_includes_dbt_findings():
    config = SlackConfig(webhook_url="https://hooks.slack.com/test", on_error=True)
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        send_slack_alert(config, [], [_dbt_finding("error")])
        mock_open.assert_called_once()
