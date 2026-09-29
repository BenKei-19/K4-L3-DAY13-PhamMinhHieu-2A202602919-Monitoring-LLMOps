"""Dashboard 6 panel đọc `data/logs.jsonl` theo contract `config/dashboard.yaml`.

    python scripts/dashboard.py                            # mở http://127.0.0.1:8501, tự refresh
    python scripts/dashboard.py --output data/dashboard.html  # ghi một file HTML tĩnh

Tên panel, đơn vị, time range, refresh và threshold đều lấy từ contract, nên
dashboard runtime và `validate_dashboard.py` luôn dùng cùng một nguồn cấu hình.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile
from scripts.validate_dashboard import load_dashboard_config

LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
CURRENT_RATE_MINUTES = 5
CHART_JS = "https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"


# ---------------------------------------------------------------- data


def load_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _minute(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def _numbers(records: list[dict], event: str, field: str) -> list[float]:
    return [
        r[field]
        for r in records
        if r.get("event") == event and isinstance(r.get(field), (int, float))
        and not isinstance(r.get(field), bool)
    ]


def _pct(values: list[float], p: int) -> float | None:
    return percentile(values, p) if values else None


def _ratio_pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 2) if whole else None


def _error_stats(records: list[dict]) -> tuple[int, int, float | None, float | None]:
    received = sum(1 for r in records if r.get("event") == "request_received")
    failed = sum(1 for r in records if r.get("event") == "request_failed")
    tool_results = [r["tool_success"] for r in records if isinstance(r.get("tool_success"), bool)]
    return (
        received,
        failed,
        _ratio_pct(failed, received),
        _ratio_pct(sum(tool_results), len(tool_results)),
    )


def _panel_latency(window: list[dict], buckets: list[list[dict]]) -> dict:
    latency = _numbers(window, "response_sent", "latency_ms")
    ttft = _numbers(window, "response_sent", "ttft_ms")
    series = []
    for name, field, p in (("P50", "latency_ms", 50), ("P95", "latency_ms", 95),
                           ("P99", "latency_ms", 99), ("TTFT P95", "ttft_ms", 95)):
        series.append({"name": name, "data": [_pct(_numbers(b, "response_sent", field), p) for b in buckets]})
    return {
        "chart": "line",
        "summary": {"p50": _pct(latency, 50), "p95": _pct(latency, 95),
                    "p99": _pct(latency, 99), "ttft_p95": _pct(ttft, 95)},
        "stats": [("P50", _pct(latency, 50), "ms"), ("P95", _pct(latency, 95), "ms"),
                  ("P99", _pct(latency, 99), "ms"), ("TTFT P95", _pct(ttft, 95), "ms")],
        "series": series,
    }


def _panel_traffic(window: list[dict], buckets: list[list[dict]]) -> dict:
    per_minute = [sum(1 for r in b if r.get("event") == "request_received") for b in buckets]
    recent = per_minute[-CURRENT_RATE_MINUTES:]
    rate = round(sum(recent) / len(recent), 2)
    return {
        "chart": "bar",
        "summary": {"count": sum(per_minute), "rate_per_minute": rate},
        "stats": [("Tổng request", sum(per_minute), ""),
                  (f"Tốc độ {CURRENT_RATE_MINUTES} phút gần nhất", rate, "req/phút")],
        "series": [{"name": "Request/phút", "data": per_minute}],
    }


def _panel_errors(window: list[dict], buckets: list[list[dict]]) -> dict:
    received, failed, error_rate, tool_rate = _error_stats(window)
    breakdown = Counter(
        r.get("error_type") or "unknown" for r in window if r.get("event") == "request_failed"
    )
    per_minute = [_error_stats(b) for b in buckets]
    return {
        "chart": "line",
        "summary": {"error_rate_pct": error_rate, "count_by_value": dict(breakdown),
                    "tool_success_rate_pct": tool_rate},
        "stats": [("Error rate", error_rate, "%"), ("Retrieval success", tool_rate, "%"),
                  ("Request lỗi", f"{failed}/{received}", "")],
        "breakdown": dict(breakdown),
        "series": [{"name": "Error rate %", "data": [m[2] for m in per_minute]},
                   {"name": "Retrieval success %", "data": [m[3] for m in per_minute]}],
    }


def _panel_cost(window: list[dict], buckets: list[list[dict]]) -> dict:
    per_minute = [round(sum(_numbers(b, "response_sent", "cost_usd")), 6) for b in buckets]
    costs = _numbers(window, "response_sent", "cost_usd")
    # None rather than 0 when there is no traffic, so the panel shows "no data" instead of "ok".
    total = round(sum(costs), 6) if costs else None
    return {
        "chart": "bar",
        "summary": {"sum_by_minute": per_minute, "total": total},
        "stats": [("Tổng", total, "USD"),
                  ("Trung bình/request", round(mean(costs), 6) if costs else None, "USD")],
        "series": [{"name": "Cost/phút (USD)", "data": per_minute}],
    }


def _panel_tokens(window: list[dict], buckets: list[list[dict]]) -> dict:
    has_data = any(r.get("event") == "response_sent" for r in window)
    tokens_in = int(sum(_numbers(window, "response_sent", "tokens_in"))) if has_data else None
    tokens_out = int(sum(_numbers(window, "response_sent", "tokens_out"))) if has_data else None
    return {
        "chart": "bar",
        "summary": {
            "sum_by_field": {"tokens_in": tokens_in, "tokens_out": tokens_out} if has_data else None
        },
        "stats": [("Tổng input", tokens_in, "tokens"), ("Tổng output", tokens_out, "tokens")],
        "series": [
            {"name": "Input tokens", "data": [int(sum(_numbers(b, "response_sent", "tokens_in"))) for b in buckets]},
            {"name": "Output tokens", "data": [int(sum(_numbers(b, "response_sent", "tokens_out"))) for b in buckets]},
        ],
    }


def _panel_quality(window: list[dict], buckets: list[list[dict]]) -> dict:
    scores = _numbers(window, "response_sent", "quality_score")
    avg = round(mean(scores), 3) if scores else None
    per_minute = []
    for b in buckets:
        values = _numbers(b, "response_sent", "quality_score")
        per_minute.append(round(mean(values), 3) if values else None)
    return {
        "chart": "line",
        "summary": {"mean": avg},
        "stats": [("Trung bình", avg, "điểm")],
        "series": [{"name": "Quality trung bình", "data": per_minute}],
    }


PANEL_BUILDERS = {
    "latency": _panel_latency,
    "traffic": _panel_traffic,
    "errors": _panel_errors,
    "cost": _panel_cost,
    "tokens": _panel_tokens,
    "quality": _panel_quality,
}
# Chỉ vẽ threshold line khi threshold cùng đơn vị với trục của biểu đồ theo phút.
THRESHOLD_ON_CHART = {"latency", "traffic", "errors", "quality"}


def threshold_status(threshold: dict, summary: dict) -> str:
    value = summary.get(threshold["aggregation"])
    if isinstance(value, dict):
        # sum_by_field: mọi field đều phải thỏa threshold, nên so field lớn nhất.
        value = max(value.values()) if value else None
    if value is None:
        return "no_data"
    limit = threshold["value"]
    ok = value <= limit if threshold["operator"] == "lte" else value >= limit
    return "ok" if ok else "breach"


def compute_dashboard(records: list[dict], config: dict, now: datetime | None = None) -> dict:
    dashboard = config["dashboard"]
    minutes = dashboard["time_range_minutes"]
    now = now or datetime.now(timezone.utc)
    end = _minute(now)
    starts = [end - timedelta(minutes=minutes - 1 - i) for i in range(minutes)]
    by_minute: dict[datetime, list[dict]] = {start: [] for start in starts}
    for record in records:
        ts = _parse_ts(record.get("ts"))
        if ts is None or ts < starts[0] or ts > now:
            continue
        by_minute[_minute(ts)].append(record)
    buckets = [by_minute[start] for start in starts]
    window = [r for b in buckets for r in b]

    panels = []
    for spec in dashboard["panels"]:
        panel = PANEL_BUILDERS[spec["id"]](window, buckets)
        threshold = spec["threshold"]
        panel.update(
            id=spec["id"],
            title=spec["title"],
            unit=spec["unit"],
            threshold=threshold,
            status=threshold_status(threshold, panel["summary"]),
            threshold_on_chart=spec["id"] in THRESHOLD_ON_CHART,
        )
        panels.append(panel)

    return {
        "title": dashboard["title"],
        "time_range_minutes": minutes,
        "refresh_seconds": dashboard["refresh_seconds"],
        "window_start": starts[0].astimezone().strftime("%H:%M"),
        "window_end": now.astimezone().strftime("%H:%M"),
        "generated_at": now.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "labels": [start.astimezone().strftime("%H:%M") for start in starts],
        "record_count": len(window),
        "panels": panels,
    }


# ---------------------------------------------------------------- render

OPERATOR_TEXT = {"lte": "≤", "gte": "≥"}
STATUS_TEXT = {
    "ok": ("✓", "Đạt threshold"),
    "breach": ("✕", "Vượt threshold"),
    "no_data": ("–", "Chưa có dữ liệu"),
}


def _fmt(value: Any) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        # Small values (cost in USD, quality 0–1) need more decimals than latency in ms.
        text = f"{value:.6f}" if abs(value) < 1 else f"{value:,.2f}"
        return text.rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _threshold_text(panel: dict) -> str:
    t = panel["threshold"]
    return f"{t['aggregation']} {OPERATOR_TEXT[t['operator']]} {_fmt(t['value'])} {panel['unit']}"


def _table_html(panel: dict, labels: list[str]) -> str:
    header = "".join(f"<th>{html.escape(s['name'])}</th>" for s in panel["series"])
    rows = []
    for i, label in enumerate(labels):
        values = [s["data"][i] for s in panel["series"]]
        if all(v in (None, 0) for v in values):
            continue
        cells = "".join(f"<td>{_fmt(v)}</td>" for v in values)
        rows.append(f"<tr><th scope='row'>{label}</th>{cells}</tr>")
    body = "".join(rows) or f"<tr><td colspan='{len(panel['series']) + 1}'>Không có dữ liệu</td></tr>"
    return f"<table><thead><tr><th>Phút</th>{header}</tr></thead><tbody>{body}</tbody></table>"


def _panel_html(panel: dict, labels: list[str]) -> str:
    icon, status_label = STATUS_TEXT[panel["status"]]
    stats = "".join(
        f"<div class='stat'><div class='stat-label'>{html.escape(label)}</div>"
        f"<div class='stat-value'>{_fmt(value)}<span class='stat-unit'> {html.escape(unit)}</span></div></div>"
        for label, value, unit in panel["stats"]
    )
    breakdown = ""
    if panel.get("breakdown"):
        items = ", ".join(f"{html.escape(k)}: {v}" for k, v in panel["breakdown"].items())
        breakdown = f"<p class='breakdown'>Lỗi theo loại: {items}</p>"
    return f"""
<section class="panel" id="panel-{panel['id']}">
  <header class="panel-head">
    <h2>{html.escape(panel['title'])}</h2>
    <span class="status status-{panel['status']}"><span class="status-icon" aria-hidden="true">{icon}</span>{status_label}</span>
  </header>
  <p class="meta">Đơn vị: <b>{html.escape(panel['unit'])}</b> · Threshold: <b>{html.escape(_threshold_text(panel))}</b></p>
  <div class="stats">{stats}</div>
  {breakdown}
  <div class="chart"><canvas id="chart-{panel['id']}" role="img" aria-label="{html.escape(panel['title'])} theo phút"></canvas></div>
  <details><summary>Bảng số liệu theo phút</summary>{_table_html(panel, labels)}</details>
</section>"""


def render_html(data: dict, auto_refresh: bool) -> str:
    panels = "".join(_panel_html(p, data["labels"]) for p in data["panels"])
    chart_data = {
        "labels": data["labels"],
        "panels": [
            {"id": p["id"], "chart": p["chart"], "series": p["series"], "unit": p["unit"],
             "threshold": p["threshold"] if p["threshold_on_chart"] else None}
            for p in data["panels"]
        ],
    }
    payload = json.dumps(chart_data, ensure_ascii=False).replace("</", "<\\/")
    refresh = data["refresh_seconds"] if auto_refresh else 0
    empty = "" if data["record_count"] else (
        "<p class='empty'>Không có log nào trong khoảng thời gian này. "
        "Chạy API rồi <code>python scripts/load_test.py</code> để tạo dữ liệu.</p>"
    )
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(data['title'])}</title>
<style>
:root {{
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --border: rgba(11,11,11,0.10);
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --series-4: #eda100;
  --status-good: #0ca30c; --status-critical: #d03b3b;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --border: rgba(255,255,255,0.10);
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #898781;
    --grid: #2c2c2a; --axis: #383835;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --series-4: #c98500;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--page); color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 14px; }}
.page {{ max-width: 1440px; margin: 0 auto; padding: 24px 16px 48px; }}
.top h1 {{ font-size: 20px; margin: 0 0 6px; }}
.top p {{ margin: 0; color: var(--text-secondary); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 420px), 1fr));
  gap: 16px; margin-top: 20px; }}
.panel {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px;
  padding: 16px; min-width: 0; }}
.panel-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }}
.panel h2 {{ font-size: 15px; margin: 0; }}
.meta {{ color: var(--text-secondary); margin: 6px 0 12px; font-size: 13px; }}
.status {{ display: inline-flex; align-items: center; gap: 6px; font-size: 12px; white-space: nowrap;
  color: var(--text-primary); }}
.status-icon {{ font-weight: 700; }}
.status-ok .status-icon {{ color: var(--status-good); }}
.status-breach .status-icon {{ color: var(--status-critical); }}
.status-no_data .status-icon {{ color: var(--text-muted); }}
.stats {{ display: flex; flex-wrap: wrap; gap: 8px 24px; margin-bottom: 8px; }}
.stat-label {{ color: var(--text-secondary); font-size: 12px; }}
.stat-value {{ font-size: 20px; font-weight: 600; }}
.stat-unit {{ font-size: 12px; font-weight: 400; color: var(--text-secondary); }}
.breakdown {{ color: var(--text-secondary); margin: 0 0 8px; font-size: 12px; }}
.chart {{ position: relative; height: 220px; }}
details {{ margin-top: 10px; color: var(--text-secondary); }}
summary {{ cursor: pointer; font-size: 12px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 12px;
  font-variant-numeric: tabular-nums; }}
th, td {{ text-align: right; padding: 4px 6px; border-bottom: 1px solid var(--grid); }}
th:first-child {{ text-align: left; }}
.empty {{ margin-top: 16px; padding: 12px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--surface-1); }}
</style>
</head>
<body>
<main class="page">
  <div class="top">
    <h1>{html.escape(data['title'])}</h1>
    <p>Khoảng thời gian: <b>{data['time_range_minutes']} phút gần nhất</b> ({data['window_start']}–{data['window_end']})
      · Tự refresh: <b>{data['refresh_seconds']} giây</b> · Cập nhật lúc {data['generated_at']}
      · Nguồn: data/logs.jsonl ({data['record_count']} bản ghi trong cửa sổ)</p>
  </div>
  {empty}
  <div class="grid">{panels}</div>
</main>
<script id="chart-data" type="application/json">{payload}</script>
<script src="{CHART_JS}"></script>
<script>
(() => {{
  const refresh = {refresh};
  if (refresh) setTimeout(() => location.reload(), refresh * 1000);
  if (!window.Chart) return;
  const data = JSON.parse(document.getElementById("chart-data").textContent);
  const css = getComputedStyle(document.documentElement);
  const token = name => css.getPropertyValue(name).trim();
  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.color = token("--text-secondary");
  const ops = {{ lte: "≤", gte: "≥" }};

  for (const panel of data.panels) {{
    const isLine = panel.chart === "line";
    const datasets = panel.series.map((s, i) => ({{
      type: panel.chart,
      label: s.name,
      data: s.data,
      borderColor: token(`--series-${{i + 1}}`),
      backgroundColor: token(`--series-${{i + 1}}`),
      borderWidth: isLine ? 2 : 0,
      pointRadius: isLine ? 4 : 0,
      pointHoverRadius: 6,
      pointBorderColor: token("--surface-1"),
      pointBorderWidth: 2,
      spanGaps: false,
      borderRadius: isLine ? 0 : 4,
      borderSkipped: "start",
      maxBarThickness: 18,
    }}));
    if (panel.threshold) {{
      const t = panel.threshold;
      datasets.push({{
        type: "line",
        label: `Threshold ${{t.aggregation}} ${{ops[t.operator]}} ${{t.value}}`,
        data: data.labels.map(() => t.value),
        borderColor: token("--text-secondary"),
        borderDash: [6, 4],
        borderWidth: 1.5,
        pointRadius: 0,
        pointHitRadius: 0,
      }});
    }}
    new Chart(document.getElementById(`chart-${{panel.id}}`), {{
      data: {{ labels: data.labels, datasets }},
      options: {{
        maintainAspectRatio: false,
        animation: false,
        interaction: {{ mode: "index", intersect: false }},
        plugins: {{
          legend: {{ display: datasets.length > 1, position: "bottom",
            labels: {{ boxWidth: 12, boxHeight: 12, usePointStyle: true }} }},
          tooltip: {{ filter: item => item.raw !== null }},
        }},
        scales: {{
          x: {{ grid: {{ display: false }}, border: {{ color: token("--axis") }},
            ticks: {{ maxTicksLimit: 7, maxRotation: 0 }} }},
          y: {{ beginAtZero: true, suggestedMax: panel.unit === "score_0_to_1" ? 1 : undefined,
            grid: {{ color: token("--grid") }}, border: {{ display: false }},
            title: {{ display: true, text: panel.unit }} }},
        }},
      }},
    }});
  }}
}})();
</script>
</body>
</html>"""


def build_page(auto_refresh: bool) -> str:
    config = load_dashboard_config(CONFIG_PATH)
    return render_html(compute_dashboard(load_records(LOG_PATH), config), auto_refresh)


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = build_page(auto_refresh=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return None


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Dashboard 6 panel từ data/logs.jsonl")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--output", type=Path, help="Ghi HTML tĩnh ra file thay vì chạy server")
    args = parser.parse_args()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(build_page(auto_refresh=False), encoding="utf-8")
        print(f"Đã ghi dashboard: {args.output}")
        return

    server = ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler)
    print(f"Dashboard: http://127.0.0.1:{args.port}  (Ctrl+C để dừng)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
