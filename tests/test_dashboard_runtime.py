from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts import dashboard
from scripts.validate_dashboard import load_dashboard_config

NOW = datetime(2026, 9, 29, 7, 0, 30, tzinfo=timezone.utc)


def _ts(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def _request(minutes_ago: float, latency_ms: int, cost_usd: float = 0.002) -> list[dict]:
    return [
        {"ts": _ts(minutes_ago), "event": "request_received", "service": "api"},
        {
            "ts": _ts(minutes_ago),
            "event": "response_sent",
            "service": "api",
            "latency_ms": latency_ms,
            "ttft_ms": 50,
            "tokens_in": 30,
            "tokens_out": 100,
            "cost_usd": cost_usd,
            "quality_score": 0.9,
            "tool_name": "retrieval",
            "tool_success": True,
        },
    ]


def _failed(minutes_ago: float) -> list[dict]:
    return [
        {"ts": _ts(minutes_ago), "event": "request_received", "service": "api"},
        {
            "ts": _ts(minutes_ago),
            "event": "request_failed",
            "service": "api",
            "error_type": "RuntimeError",
            "tool_name": "retrieval",
            "tool_success": False,
        },
    ]


def _panels(records: list[dict]) -> dict[str, dict]:
    config = load_dashboard_config(dashboard.CONFIG_PATH)
    data = dashboard.compute_dashboard(records, config, now=NOW)
    return {panel["id"]: panel for panel in data["panels"]}


def test_dashboard_has_the_six_contract_panels_over_60_minutes() -> None:
    config = load_dashboard_config(dashboard.CONFIG_PATH)
    data = dashboard.compute_dashboard([], config, now=NOW)

    assert [p["id"] for p in data["panels"]] == ["latency", "traffic", "errors", "cost", "tokens", "quality"]
    assert len(data["labels"]) == 60
    assert all(p["status"] == "no_data" for p in data["panels"] if p["id"] != "traffic")


def test_dashboard_ignores_records_outside_the_time_window() -> None:
    panels = _panels(_request(minutes_ago=90, latency_ms=100) + _request(minutes_ago=1, latency_ms=200))

    assert panels["traffic"]["summary"]["count"] == 1
    assert panels["latency"]["summary"]["p50"] == 200


def test_dashboard_computes_errors_and_retrieval_success() -> None:
    records = []
    for i in range(3):
        records += _request(minutes_ago=2, latency_ms=300 + i)
    records += _failed(minutes_ago=2)

    errors = _panels(records)["errors"]

    assert errors["summary"]["error_rate_pct"] == 25.0
    assert errors["summary"]["tool_success_rate_pct"] == 75.0
    assert errors["summary"]["count_by_value"] == {"RuntimeError": 1}
    assert errors["status"] == "breach"


def test_dashboard_latency_breach_uses_contract_threshold() -> None:
    records = []
    for _ in range(20):
        records += _request(minutes_ago=3, latency_ms=3500)

    panels = _panels(records)

    assert panels["latency"]["summary"]["p95"] == 3500
    assert panels["latency"]["status"] == "breach"
    assert panels["quality"]["status"] == "ok"
    assert panels["traffic"]["summary"]["rate_per_minute"] == 4.0


def test_threshold_status_for_sum_by_field_checks_every_field() -> None:
    threshold = {"aggregation": "sum_by_field", "operator": "lte", "value": 100}

    assert dashboard.threshold_status(threshold, {"sum_by_field": {"in": 50, "out": 90}}) == "ok"
    assert dashboard.threshold_status(threshold, {"sum_by_field": {"in": 50, "out": 150}}) == "breach"


def test_render_html_shows_time_range_units_and_thresholds() -> None:
    config = load_dashboard_config(dashboard.CONFIG_PATH)
    data = dashboard.compute_dashboard(_request(minutes_ago=1, latency_ms=200), config, now=NOW)

    page = dashboard.render_html(data, auto_refresh=True)

    assert "60 phút gần nhất" in page
    assert "30 giây" in page
    assert "p95 ≤ 3,000 ms" in page
    assert page.count('class="panel"') == 6
