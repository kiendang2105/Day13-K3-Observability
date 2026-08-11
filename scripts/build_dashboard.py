"""Dung dashboard 6 panel tu data/logs.jsonl theo dung config/dashboard.yaml.

    python scripts/build_dashboard.py                 # dung 1 lan roi thoat
    python scripts/build_dashboard.py --watch         # dung lai moi 30s (live)
    python scripts/build_dashboard.py --anchor latest # neo cua so vao log moi nhat

Sinh ra mot file HTML tu chua (khong CDN, khong dependency moi), mo bang browser
la chup duoc evidence. Nguon du lieu la data/logs.jsonl - dung nguon chuan ma
README.md quy dinh, khong phai endpoint /metrics (endpoint do chi la bo dem cong
don trong RAM, khong co truc thoi gian nen khong dung duoc cho cua so 60 phut).
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

CONFIG_PATH = REPO_ROOT / "config" / "dashboard.yaml"
LOG_PATH = REPO_ROOT / "data" / "logs.jsonl"
OUT_PATH = REPO_ROOT / "data" / "dashboard.html"

# 3 slot dau cua bang mau tham chieu, giu nguyen thu tu. Thu tu slot chinh la co
# che an toan cho nguoi mu mau - doi cho hoac tu che mau moi la pha vo no.
SERIES_LIGHT = ("#2a78d6", "#eb6834", "#1baf7a")
SERIES_DARK = ("#3987e5", "#d95926", "#199e70")

PLOT_W, PLOT_H = 640, 170
PAD_L, PAD_R, PAD_T, PAD_B = 52, 14, 18, 26


# --------------------------------------------------------------------------- #
# Doc du lieu
# --------------------------------------------------------------------------- #

def parse_ts(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_ts(record.get("ts", ""))
        if ts is None:
            continue
        record["_ts"] = ts
        records.append(record)
    return sorted(records, key=lambda r: r["_ts"])


def resolve_window(records: list[dict], minutes: int, anchor: str) -> tuple[datetime, datetime, bool]:
    """Tra ve (start, end, da_fallback).

    Mac dinh neo cua so vao thoi diem hien tai. Neu cua so do rong (log cu hon 60
    phut) thi neo vao ban ghi moi nhat va bao ro, thay vi ve mot dashboard trong
    khien nguoi doc tuong he thong khong co traffic.
    """
    now = datetime.now(timezone.utc)
    if anchor == "latest" and records:
        end = records[-1]["_ts"]
        return end - timedelta(minutes=minutes), end, False

    start = now - timedelta(minutes=minutes)
    if any(r["_ts"] >= start for r in records) or not records:
        return start, now, False

    end = records[-1]["_ts"]
    return end - timedelta(minutes=minutes), end, True


def minute_buckets(start: datetime, end: datetime) -> list[datetime]:
    first = start.replace(second=0, microsecond=0)
    buckets, cursor = [], first
    while cursor <= end:
        buckets.append(cursor)
        cursor += timedelta(minutes=1)
    return buckets


def bucket_of(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


# --------------------------------------------------------------------------- #
# Phep tinh
# --------------------------------------------------------------------------- #

def percentile(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (p / 100) * (len(ordered) - 1)
    low, high = int(rank), min(int(rank) + 1, len(ordered) - 1)
    return float(ordered[low] + (ordered[high] - ordered[low]) * (rank - low))


def evaluate(value: float, threshold: dict) -> bool:
    limit = threshold["value"]
    return value <= limit if threshold["operator"] == "lte" else value >= limit


def fmt(value: float, digits: int = 0) -> str:
    if digits == 0:
        return f"{value:,.0f}".replace(",", " ")
    return f"{value:,.{digits}f}".replace(",", " ")


# --------------------------------------------------------------------------- #
# Ve SVG
# --------------------------------------------------------------------------- #

def _scale_y(value: float, vmax: float) -> float:
    if vmax <= 0:
        return PAD_T + PLOT_H
    return PAD_T + PLOT_H - (value / vmax) * PLOT_H


def _rounded_top(x: float, y: float, w: float, h: float, r: float = 4.0) -> str:
    """Cot co 2 goc tren bo tron, chan cot neo thang vao baseline."""
    r = min(r, w / 2, h) if h > 0 else 0
    bottom = PAD_T + PLOT_H
    return (
        f"M{x:.1f},{bottom:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
        f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
        f"V{bottom:.1f} Z"
    )


def _chrome(buckets: list[datetime], vmax: float, unit: str) -> str:
    """Luoi + truc: hairline lien net, mot bac lech so voi nen (khong dut net)."""
    parts = []
    for i in range(5):
        value = vmax * (4 - i) / 4
        y = _scale_y(value, vmax)
        parts.append(
            f'<line class="grid" x1="{PAD_L}" y1="{y:.1f}" x2="{PAD_L + PLOT_W}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'<text class="tick" x="{PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end">'
            f"{fmt(value, 2 if vmax < 10 else 0)}</text>"
        )
    baseline = PAD_T + PLOT_H
    parts.append(
        f'<line class="axis" x1="{PAD_L}" y1="{baseline}" x2="{PAD_L + PLOT_W}" y2="{baseline}"/>'
    )

    step = max(1, len(buckets) // 6)
    slot = PLOT_W / max(1, len(buckets))
    for i in range(0, len(buckets), step):
        x = PAD_L + i * slot + slot / 2
        parts.append(
            f'<text class="tick" x="{x:.1f}" y="{baseline + 16}" text-anchor="middle">'
            f"{buckets[i].astimezone().strftime('%H:%M')}</text>"
        )
    # Don vi khong ve trong khung: no dung ngay tren nhan tick cao nhat va de len
    # nhau. Header cua panel va cac o KPI da ghi don vi roi.
    return "".join(parts)


def _threshold_line(threshold: dict, vmax: float, label: str) -> str:
    """Duong nguong: dut net co chu dich - dut net chi danh rieng cho nguong."""
    limit = threshold["value"]
    if vmax <= 0 or limit > vmax * 1.6:
        return ""
    y = _scale_y(min(limit, vmax), vmax)
    return (
        f'<line class="threshold" x1="{PAD_L}" y1="{y:.1f}" x2="{PAD_L + PLOT_W}" y2="{y:.1f}"/>'
        f'<text class="threshold-label" x="{PAD_L + PLOT_W}" y="{y - 6:.1f}" text-anchor="end">'
        f"{html.escape(label)}</text>"
    )


def svg_columns(buckets, values, threshold=None, threshold_label="", unit="", series_index=0):
    vmax = max([*values, threshold["value"] if threshold else 0, 1e-9])
    vmax *= 1.15
    slot = PLOT_W / max(1, len(buckets))
    bar_w = max(2.0, slot - 2)  # khe 2px giua cac cot, khong ve vien

    bars = []
    for i, value in enumerate(values):
        if value <= 0:
            continue
        x = PAD_L + i * slot + (slot - bar_w) / 2
        y = _scale_y(value, vmax)
        label = f"{buckets[i].astimezone().strftime('%H:%M')} · {fmt(value, 4 if vmax < 1 else 0)} {unit}"
        bars.append(
            f'<path class="bar s{series_index}" d="{_rounded_top(x, y, bar_w, PAD_T + PLOT_H - y)}">'
            f"<title>{html.escape(label)}</title></path>"
        )

    return (
        f'<svg viewBox="0 0 {PAD_L + PLOT_W + PAD_R} {PAD_T + PLOT_H + PAD_B}" '
        f'role="img" preserveAspectRatio="xMidYMid meet">'
        f'{_chrome(buckets, vmax, unit)}{"".join(bars)}'
        f'{_threshold_line(threshold, vmax, threshold_label) if threshold else ""}</svg>'
    )


def svg_grouped_columns(buckets, series, unit="", threshold=None, threshold_label=""):
    flat = [v for _, values in series for v in values]
    vmax = max([*flat, 1e-9]) * 1.15
    slot = PLOT_W / max(1, len(buckets))
    bar_w = max(2.0, (slot - 2) / len(series) - 2)

    bars = []
    for si, (name, values) in enumerate(series):
        for i, value in enumerate(values):
            if value <= 0:
                continue
            group_x = PAD_L + i * slot + (slot - (bar_w + 2) * len(series)) / 2
            x = group_x + si * (bar_w + 2)
            y = _scale_y(value, vmax)
            label = f"{buckets[i].astimezone().strftime('%H:%M')} · {name}: {fmt(value)} {unit}"
            bars.append(
                f'<path class="bar s{si}" d="{_rounded_top(x, y, bar_w, PAD_T + PLOT_H - y)}">'
                f"<title>{html.escape(label)}</title></path>"
            )

    return (
        f'<svg viewBox="0 0 {PAD_L + PLOT_W + PAD_R} {PAD_T + PLOT_H + PAD_B}" '
        f'role="img" preserveAspectRatio="xMidYMid meet">'
        f'{_chrome(buckets, vmax, unit)}{"".join(bars)}'
        f'{_threshold_line(threshold, vmax, threshold_label) if threshold else ""}</svg>'
    )


def svg_lines(buckets, series, threshold=None, threshold_label="", unit=""):
    """Nhieu duong. Phut khong co du lieu bi ngat doan thay vi noi thang qua -
    noi qua khoang trong la bia ra du lieu khong ton tai."""
    flat = [v for _, values in series for v in values if v is not None]
    vmax = max([*flat, threshold["value"] if threshold else 0, 1e-9]) * 1.15
    slot = PLOT_W / max(1, len(buckets))

    marks = []
    for si, (name, values) in enumerate(series):
        run: list[tuple[float, float]] = []
        for i, value in enumerate(values):
            if value is None:
                if len(run) > 1:
                    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in run)
                    marks.append(f'<polyline class="line s{si}" points="{points}"/>')
                run = []
                continue
            x = PAD_L + i * slot + slot / 2
            run.append((x, _scale_y(value, vmax)))
        if len(run) > 1:
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y in run)
            marks.append(f'<polyline class="line s{si}" points="{points}"/>')

        for i, value in enumerate(values):
            if value is None:
                continue
            x = PAD_L + i * slot + slot / 2
            y = _scale_y(value, vmax)
            label = f"{buckets[i].astimezone().strftime('%H:%M')} · {name}: {fmt(value, 2 if vmax < 10 else 0)} {unit}"
            marks.append(
                f'<circle class="dot s{si}" cx="{x:.1f}" cy="{y:.1f}" r="4">'
                f"<title>{html.escape(label)}</title></circle>"
            )

    return (
        f'<svg viewBox="0 0 {PAD_L + PLOT_W + PAD_R} {PAD_T + PLOT_H + PAD_B}" '
        f'role="img" preserveAspectRatio="xMidYMid meet">'
        f'{_chrome(buckets, vmax, unit)}{"".join(marks)}'
        f'{_threshold_line(threshold, vmax, threshold_label) if threshold else ""}</svg>'
    )


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

CSS = """
*{box-sizing:border-box}
.viz-root{
  color-scheme:light;
  --surface-1:#fcfcfb; --plane:#f9f9f7;
  --text-primary:#0b0b0b; --text-secondary:#52514e; --muted:#898781;
  --grid:#e1e0d9; --baseline:#c3c2b7; --border:rgba(11,11,11,0.10);
  --s0:#2a78d6; --s1:#eb6834; --s2:#1baf7a;
  --good:#0ca30c; --critical:#d03b3b;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]) .viz-root{
    color-scheme:dark;
    --surface-1:#1a1a19; --plane:#0d0d0d;
    --text-primary:#ffffff; --text-secondary:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --baseline:#383835; --border:rgba(255,255,255,0.10);
    --s0:#3987e5; --s1:#d95926; --s2:#199e70;
  }
}
body{margin:0;padding:24px;background:var(--plane);color:var(--text-primary);
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header.page{max-width:1400px;margin:0 auto 20px}
h1{margin:0 0 6px;font-size:22px;font-weight:650}
.meta{color:var(--text-secondary);font-size:13px;display:flex;gap:18px;flex-wrap:wrap}
.meta b{color:var(--text-primary);font-weight:600}
.notice{max-width:1400px;margin:0 auto 16px;padding:10px 14px;border-radius:8px;
  border:1px solid var(--border);background:var(--surface-1);color:var(--text-secondary)}
.grid{max-width:1400px;margin:0 auto;display:grid;gap:16px;
  grid-template-columns:repeat(auto-fit,minmax(480px,1fr))}
.panel{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:16px 18px 12px}
.panel-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:2px}
.panel-head h2{margin:0;font-size:15px;font-weight:620}
.panel-id{color:var(--muted);font-size:12px;font-family:ui-monospace,monospace}
.badge{margin-left:auto;font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px;
  border:1px solid var(--border);white-space:nowrap}
.badge.pass{color:var(--good)} .badge.fail{color:var(--critical)}
.kpis{display:flex;gap:22px;flex-wrap:wrap;margin:12px 0 4px}
.kpi{display:flex;flex-direction:column;gap:1px}
.kpi .v{font-size:24px;font-weight:640;letter-spacing:-0.01em}
.kpi .k{font-size:12px;color:var(--text-secondary)}
.swatch{width:9px;height:9px;border-radius:2px;display:inline-block;margin-right:5px;vertical-align:baseline}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--text-secondary);margin:2px 0 6px}
figure{margin:0}
svg{width:100%;height:auto;display:block;overflow:visible}
.grid line,line.grid{stroke:var(--grid);stroke-width:1}
line.axis{stroke:var(--baseline);stroke-width:1}
text.tick{fill:var(--muted);font-size:10px;font-variant-numeric:tabular-nums}
line.threshold{stroke:var(--critical);stroke-width:1.5;stroke-dasharray:5 4}
text.threshold-label{fill:var(--critical);font-size:10px;font-weight:600}
path.bar.s0{fill:var(--s0)} path.bar.s1{fill:var(--s1)} path.bar.s2{fill:var(--s2)}
polyline.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
polyline.line.s0{stroke:var(--s0)} polyline.line.s1{stroke:var(--s1)} polyline.line.s2{stroke:var(--s2)}
circle.dot{stroke:var(--surface-1);stroke-width:2}
circle.dot.s0{fill:var(--s0)} circle.dot.s1{fill:var(--s1)} circle.dot.s2{fill:var(--s2)}
figcaption{color:var(--text-secondary);font-size:12px;margin-top:8px}
details{margin-top:8px;font-size:12px}
summary{cursor:pointer;color:var(--text-secondary);padding:4px 0}
table{border-collapse:collapse;width:100%;margin-top:6px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:4px 8px;border-bottom:1px solid var(--grid)}
th:first-child,td:first-child{text-align:left}
th{color:var(--text-secondary);font-weight:600}
.empty{color:var(--muted);padding:28px 0;text-align:center}
footer{max-width:1400px;margin:20px auto 0;color:var(--muted);font-size:12px}
"""


def badge(passed: bool, text: str) -> str:
    # Mau trang thai luon di kem icon + chu, khong bao gio dung mau don doc.
    icon = "✓" if passed else "✕"
    tone = "pass" if passed else "fail"
    return f'<span class="badge {tone}">{icon} {html.escape(text)}</span>'


def kpi(value: str, key: str, series_index: int | None = None) -> str:
    swatch = f'<span class="swatch" style="background:var(--s{series_index})"></span>' if series_index is not None else ""
    return f'<div class="kpi"><span class="v">{swatch}{html.escape(value)}</span><span class="k">{html.escape(key)}</span></div>'


def legend(names: list[str]) -> str:
    # Legend luon co khi >= 2 series; 1 series thi tieu de da goi ten no roi.
    if len(names) < 2:
        return ""
    items = "".join(
        f'<span><span class="swatch" style="background:var(--s{i})"></span>{html.escape(n)}</span>'
        for i, n in enumerate(names)
    )
    return f'<div class="legend">{items}</div>'


def table_view(headers: list[str], rows: list[list[str]], caption: str = "Dạng bảng") -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    return (
        f"<details><summary>{html.escape(caption)} ({len(rows)} dòng)</summary>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></details>"
    )


def panel(spec: dict, badge_html: str, body: str) -> str:
    return (
        f'<section class="panel"><div class="panel-head">'
        f'<h2>{html.escape(spec["title"])}</h2>'
        f'<span class="panel-id">{html.escape(spec["id"])} · {html.escape(spec["unit"])}</span>'
        f"{badge_html}</div>{body}</section>"
    )


# --------------------------------------------------------------------------- #
# Dung tung panel
# --------------------------------------------------------------------------- #

def build_panels(specs: dict, records: list[dict], buckets: list[datetime]) -> tuple[str, list[tuple[str, bool, str]]]:
    sent = [r for r in records if r.get("event") == "response_sent"]
    received = [r for r in records if r.get("event") == "request_received"]
    failed = [r for r in records if r.get("event") == "request_failed"]

    by_minute: dict[datetime, list[dict]] = defaultdict(list)
    for record in sent:
        by_minute[bucket_of(record["_ts"])].append(record)
    received_by_minute: Counter[datetime] = Counter(bucket_of(r["_ts"]) for r in received)

    out: list[str] = []
    status: list[tuple[str, bool, str]] = []

    def field_series(field: str, reducer) -> list:
        return [reducer([r.get(field, 0) or 0 for r in by_minute.get(b, [])]) for b in buckets]

    # 1. Latency ---------------------------------------------------------- #
    spec = specs["latency"]
    limit = spec["threshold"]["value"]
    latencies = [r.get("latency_ms", 0) or 0 for r in sent]
    p50, p95, p99 = (percentile(latencies, p) for p in (50, 95, 99))
    series = [
        (name, [percentile([r.get("latency_ms", 0) or 0 for r in by_minute[b]], p) if by_minute.get(b) else None
                for b in buckets])
        for name, p in (("P50", 50), ("P95", 95), ("P99", 99))
    ]
    passed = evaluate(p95, spec["threshold"])
    status.append((spec["id"], passed, f"P95 {fmt(p95)} ms"))
    rows = [
        [b.astimezone().strftime("%H:%M")] + [fmt(vals[i]) if vals[i] is not None else "—" for _, vals in series]
        for i, b in enumerate(buckets) if by_minute.get(b)
    ]
    kpis = kpi(f"{fmt(p50)} ms", "P50", 0) + kpi(f"{fmt(p95)} ms", "P95", 1) + kpi(f"{fmt(p99)} ms", "P99", 2)
    chart = svg_lines(buckets, series, spec["threshold"], f"SLO {fmt(limit)} ms", "ms")
    out.append(panel(spec, badge(passed, f"SLO P95 ≤ {fmt(limit)} ms"),
        f'<div class="kpis">{kpis}</div>{legend(["P50", "P95", "P99"])}'
        f"<figure>{chart}</figure>"
        f"<figcaption>Percentile tính trên <code>response_sent.latency_ms</code>. "
        f"Phút không có request bị ngắt đoạn thay vì nối thẳng qua.</figcaption>"
        f'{table_view(["Phút", "P50 (ms)", "P95 (ms)", "P99 (ms)"], rows)}'))

    # 2. Traffic ---------------------------------------------------------- #
    spec = specs["traffic"]
    limit = spec["threshold"]["value"]
    counts = [received_by_minute.get(b, 0) for b in buckets]
    total = len(received)
    active = [c for c in counts if c > 0]
    rate = round(total / len(active), 2) if active else 0.0
    passed = evaluate(rate, spec["threshold"])
    status.append((spec["id"], passed, f"{rate} req/phút"))
    kpis = (kpi(fmt(total), "Tổng request") + kpi(str(rate), "Request/phút (phút có tải)")
            + kpi(fmt(max(counts) if counts else 0), "Phút cao nhất"))
    chart = svg_columns(buckets, counts, spec["threshold"], f"≥ {fmt(limit)}/phút", "req")
    rows = [[b.astimezone().strftime("%H:%M"), fmt(c)] for b, c in zip(buckets, counts) if c]
    out.append(panel(spec, badge(passed, f"≥ {fmt(limit)} req/phút"),
        f'<div class="kpis">{kpis}</div><figure>{chart}</figure>'
        f"<figcaption>Đếm <code>request_received</code> theo từng phút. "
        f"Request/phút = tổng ÷ số phút thực sự có tải, không chia đều cho 60 phút.</figcaption>"
        f'{table_view(["Phút", "Request"], rows)}'))

    # 3. Errors ----------------------------------------------------------- #
    spec = specs["errors"]
    limit = spec["threshold"]["value"]
    error_rate = round(len(failed) / len(received) * 100, 2) if received else 0.0
    breakdown = Counter(r.get("error_type", "unknown") for r in failed)
    passed = evaluate(error_rate, spec["threshold"])
    status.append((spec["id"], passed, f"{error_rate}%"))
    if breakdown:
        rows = [[k, fmt(v)] for k, v in breakdown.most_common()]
        body = table_view(["error_type", "Số lần"], rows, "Breakdown theo loại lỗi").replace(
            "<details>", "<details open>"
        )
    else:
        body = '<p class="empty">Không có <code>request_failed</code> trong cửa sổ này.</p>'
    kpis = (kpi(f"{error_rate}%", "Error rate") + kpi(fmt(len(failed)), "Request lỗi")
            + kpi(fmt(len(received)), "Request nhận"))
    out.append(panel(spec, badge(passed, f"≤ {fmt(limit)}%"),
        f'<div class="kpis">{kpis}</div>{body}'
        f"<figcaption>error_rate = <code>count(request_failed) / count(request_received) × 100</code>.</figcaption>"))

    # 4. Cost ------------------------------------------------------------- #
    spec = specs["cost"]
    limit = spec["threshold"]["value"]
    per_minute = field_series("cost_usd", sum)
    total_cost = sum(r.get("cost_usd", 0) or 0 for r in sent)
    avg_cost = total_cost / len(sent) if sent else 0.0
    passed = evaluate(total_cost, spec["threshold"])
    status.append((spec["id"], passed, f"{total_cost:.4f} USD"))
    kpis = kpi(f"{total_cost:.4f} USD", "Tổng chi phí") + kpi(f"{avg_cost:.5f} USD", "Trung bình / request")
    chart = svg_columns(buckets, per_minute, None, "", "USD")
    rows = [[b.astimezone().strftime("%H:%M"), f"{v:.5f}"] for b, v in zip(buckets, per_minute) if v]
    out.append(panel(spec, badge(passed, f"≤ {limit} USD"),
        f'<div class="kpis">{kpis}</div><figure>{chart}</figure>'
        f"<figcaption>Tổng <code>response_sent.cost_usd</code> theo phút. Ngưỡng {limit} USD là ngân sách "
        f"của cả cửa sổ nên không vẽ thành đường trên trục theo phút.</figcaption>"
        f'{table_view(["Phút", "Chi phí (USD)"], rows)}'))

    # 5. Tokens ----------------------------------------------------------- #
    spec = specs["tokens"]
    limit = spec["threshold"]["value"]
    tokens_in = field_series("tokens_in", sum)
    tokens_out = field_series("tokens_out", sum)
    sum_in, sum_out = sum(tokens_in), sum(tokens_out)
    passed = evaluate(max(sum_in, sum_out), spec["threshold"])
    status.append((spec["id"], passed, f"in {fmt(sum_in)} / out {fmt(sum_out)}"))
    kpis = (kpi(fmt(sum_in), "Tokens in", 0) + kpi(fmt(sum_out), "Tokens out", 1)
            + kpi(fmt(sum_in + sum_out), "Tổng"))
    chart = svg_grouped_columns(buckets, [("Tokens in", tokens_in), ("Tokens out", tokens_out)], "tokens")
    rows = [[b.astimezone().strftime("%H:%M"), fmt(i), fmt(o)]
            for b, i, o in zip(buckets, tokens_in, tokens_out) if i or o]
    out.append(panel(spec, badge(passed, f"mỗi chiều ≤ {fmt(limit)}"),
        f'<div class="kpis">{kpis}</div>{legend(["Tokens in", "Tokens out"])}'
        f"<figure>{chart}</figure>"
        f"<figcaption>Tổng <code>tokens_in</code> và <code>tokens_out</code> theo phút, tách riêng hai chiều.</figcaption>"
        f'{table_view(["Phút", "In", "Out"], rows)}'))

    # 6. Quality ---------------------------------------------------------- #
    spec = specs["quality"]
    limit = spec["threshold"]["value"]
    scores = [r.get("quality_score", 0) or 0 for r in sent]
    avg = round(mean(scores), 4) if scores else 0.0
    per_minute_q = [round(mean([r.get("quality_score", 0) or 0 for r in by_minute[b]]), 4) if by_minute.get(b) else None
                    for b in buckets]
    passed = evaluate(avg, spec["threshold"])
    status.append((spec["id"], passed, str(avg)))
    kpis = (kpi(str(avg), "Quality trung bình") + kpi(str(min(scores)) if scores else "—", "Thấp nhất")
            + kpi(fmt(len(scores)), "Số mẫu"))
    chart = svg_lines(buckets, [("Quality", per_minute_q)], spec["threshold"], f"SLO {limit}", "score")
    rows = [[b.astimezone().strftime("%H:%M"), str(v)] for b, v in zip(buckets, per_minute_q) if v is not None]
    out.append(panel(spec, badge(passed, f"≥ {limit}"),
        f'<div class="kpis">{kpis}</div><figure>{chart}</figure>'
        f"<figcaption>Trung bình <code>response_sent.quality_score</code> theo phút, thang 0–1.</figcaption>"
        f'{table_view(["Phút", "Quality"], rows)}'))

    return "".join(out), status


def render(config: dict, records: list[dict], anchor: str) -> tuple[str, list[tuple[str, bool, str]]]:
    dashboard = config["dashboard"]
    minutes = dashboard["time_range_minutes"]
    refresh = dashboard["refresh_seconds"]
    specs = {p["id"]: p for p in dashboard["panels"]}

    start, end, fell_back = resolve_window(records, minutes, anchor)
    windowed = [r for r in records if start <= r["_ts"] <= end]
    buckets = minute_buckets(start, end)

    panels_html, status = build_panels(specs, windowed, buckets)

    notice = ""
    if fell_back:
        notice = (
            '<div class="notice">Không có log nào trong 60 phút gần đây nên cửa sổ được neo vào '
            "bản ghi mới nhất. Chạy <code>python scripts/load_test.py</code> rồi dựng lại để có dữ liệu thời gian thực.</div>"
        )

    generated = datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")
    head = (
        f'<header class="page"><h1>{html.escape(dashboard["title"])}</h1>'
        f'<div class="meta">'
        f"<span>Time range <b>{minutes} phút</b></span>"
        f"<span>{start.astimezone().strftime('%H:%M')} → {end.astimezone().strftime('%H:%M')}</span>"
        f"<span>Refresh <b>{refresh}s</b></span>"
        f"<span>Nguồn <b>data/logs.jsonl</b></span>"
        f"<span>{len(windowed)} log record</span>"
        f"<span>Dựng lúc {generated}</span>"
        f"</div></header>{notice}"
    )
    foot = (
        '<footer>Panel, đơn vị và threshold lấy trực tiếp từ <code>config/dashboard.yaml</code>. '
        "Kiểm tra contract bằng <code>python scripts/validate_dashboard.py</code>.</footer>"
    )

    html_doc = (
        f'<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="refresh" content="{refresh}">'
        f"<title>{html.escape(dashboard['title'])}</title><style>{CSS}</style></head>"
        f'<body class="viz-root">{head}<div class="grid">{panels_html}</div>{foot}</body></html>'
    )
    return html_doc, status


def build_once(config_path: Path, log_path: Path, out_path: Path, anchor: str) -> list[tuple[str, bool, str]]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    records = load_records(log_path)
    document, status = render(config, records, anchor)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(document, encoding="utf-8")
    return status


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--logs", type=Path, default=LOG_PATH)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--anchor", choices=["now", "latest"], default="now")
    parser.add_argument("--watch", action="store_true", help="Dung lai lien tuc theo refresh_seconds")
    args = parser.parse_args()

    if not args.logs.exists():
        print(f"Khong tim thay {args.logs}. Chay API va scripts/load_test.py truoc.")
        return 1

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    refresh = config["dashboard"]["refresh_seconds"]

    while True:
        status = build_once(args.config, args.logs, args.out, args.anchor)
        print(f"Da dung {args.out}")
        for panel_id, passed, value in status:
            print(f"  [{'DAT' if passed else 'VUOT NGUONG'}] {panel_id:<8} {value}")
        if not args.watch:
            print(f"\nMo bang browser:\n  file:///{args.out.resolve().as_posix()}")
            return 0
        print(f"  ... dung lai sau {refresh}s (Ctrl+C de dung)\n")
        time.sleep(refresh)


if __name__ == "__main__":
    raise SystemExit(main())
