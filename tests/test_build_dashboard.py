from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "config" / "dashboard.yaml"


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_dashboard", REPO_ROOT / "scripts" / "build_dashboard.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_builder()


def write_logs(path: Path, *, minutes_ago: int = 1, count: int = 4, failures: int = 0) -> Path:
    base = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    lines = []
    for i in range(count):
        ts = (base + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")
        common = {"ts": ts, "level": "info", "service": "api", "correlation_id": f"req-{i:08x}"}
        lines.append({**common, "event": "request_received"})
        lines.append(
            {
                **common,
                "event": "response_sent",
                "latency_ms": 1000 + i * 100,
                "tokens_in": 30,
                "tokens_out": 120,
                "cost_usd": 0.002,
                "quality_score": 0.8,
            }
        )
    for i in range(failures):
        ts = (base + timedelta(seconds=30 + i)).isoformat().replace("+00:00", "Z")
        lines.append(
            {
                "ts": ts,
                "level": "error",
                "service": "api",
                "correlation_id": f"req-f{i:07x}",
                "event": "request_failed",
                "error_type": "RuntimeError",
            }
        )
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def build(tmp_path: Path, **kwargs) -> str:
    logs = write_logs(tmp_path / "logs.jsonl", **kwargs)
    out = tmp_path / "dashboard.html"
    builder.build_once(CONTRACT, logs, out, "now")
    return out.read_text(encoding="utf-8")


def test_renders_exactly_the_six_contract_panels(tmp_path: Path) -> None:
    document = build(tmp_path)
    assert document.count('<section class="panel"') == 6
    ids = set(re.findall(r'class="panel-id">([a-z]+)', document))
    assert ids == {"latency", "traffic", "errors", "cost", "tokens", "quality"}


def test_page_is_self_contained(tmp_path: Path) -> None:
    """Khong duoc goi CDN: dashboard phai mo duoc offline luc cham bai."""
    document = build(tmp_path)
    assert not re.search(r'(?:src|href)="https?://', document)
    assert "NaN" not in document


def test_contract_drives_units_and_thresholds(tmp_path: Path) -> None:
    document = build(tmp_path)
    assert "3 000 ms" in document or "3000 ms" in document  # latency threshold
    assert "2.5 USD" in document
    assert 'class="threshold"' in document
    assert "60 phút" in document


def test_records_outside_the_window_are_excluded(tmp_path: Path) -> None:
    """Cua so 60 phut phai loai log cu, neu khong dashboard bao cao sai tai."""
    fresh = build(tmp_path, minutes_ago=1, count=4)
    stale_dir = tmp_path / "stale"
    stale_dir.mkdir()
    stale = build(stale_dir, minutes_ago=200, count=4)

    assert "8 log record" in fresh
    # Log cu hon cua so -> fallback neo vao ban ghi moi nhat, co canh bao ro rang
    assert 'class="notice"' in stale
    assert 'class="notice"' not in fresh


def test_error_panel_reports_rate_and_breakdown(tmp_path: Path) -> None:
    document = build(tmp_path, count=4, failures=1)
    assert "RuntimeError" in document
    assert "25.0%" in document  # 1 loi / 4 request nhan


def test_error_panel_has_empty_state_without_failures(tmp_path: Path) -> None:
    document = build(tmp_path, count=4, failures=0)
    assert "0.0%" in document
    assert 'class="empty"' in document


def test_every_chart_ships_a_table_view(tmp_path: Path) -> None:
    """Gia tri khong bao gio chi doc duoc bang mau."""
    document = build(tmp_path)
    assert document.count("<details") >= document.count("<figure>")


@pytest.mark.parametrize(
    ("value", "threshold", "expected"),
    [
        (2999, {"operator": "lte", "value": 3000}, True),
        (3001, {"operator": "lte", "value": 3000}, False),
        (0.8, {"operator": "gte", "value": 0.75}, True),
        (0.7, {"operator": "gte", "value": 0.75}, False),
    ],
)
def test_threshold_evaluation(value, threshold, expected) -> None:
    assert builder.evaluate(value, threshold) is expected


def test_percentile_matches_linear_interpolation() -> None:
    assert builder.percentile([10, 20, 30, 40], 50) == 25.0
    assert builder.percentile([], 95) == 0.0
    assert builder.percentile([7], 99) == 7.0
