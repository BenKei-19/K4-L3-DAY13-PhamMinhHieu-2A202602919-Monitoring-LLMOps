from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ALERT_FIELDS = ("name", "severity", "condition", "duration", "type", "channel", "owner", "runbook")


def _load(path: str) -> dict:
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


def test_three_complete_symptom_based_alerts() -> None:
    alerts = _load("config/alert_rules.yaml")["alerts"]

    assert len(alerts) == 3
    assert len({a["name"] for a in alerts}) == 3
    for alert in alerts:
        for field in REQUIRED_ALERT_FIELDS:
            assert alert.get(field), f"{alert.get('name')}: thiếu {field}"
            assert "TODO" not in str(alert[field])
        assert alert["type"] == "symptom-based"
        assert alert["channel"] == "slack"
        assert alert["slack_channel"].startswith("#")
        assert re.fullmatch(r"\d+m", alert["duration"])


def test_every_runbook_link_points_to_a_filled_section() -> None:
    alerts = _load("config/alert_rules.yaml")["alerts"]
    runbook = (REPO_ROOT / "docs" / "alerts.md").read_text(encoding="utf-8")

    for alert in alerts:
        path, anchor = alert["runbook"].split("#")
        assert path == "docs/alerts.md"
        number = anchor.removeprefix("alert-")
        section = runbook.split(f"## Alert {number}")[1].split("\n## ")[0]
        assert alert["name"] in section
        assert "Mitigation tạm thời:" in section


def test_slo_error_budget_matches_target() -> None:
    slo = _load("config/slo.yaml")["primary_slo"]

    assert slo["error_budget_percent"] == round(100 - slo["target_percent"], 3)
    assert slo["error_budget"]["per_10000_requests"] == 10000 * slo["error_budget_percent"] / 100
