"""Xac minh trace tren Langfuse co gan dung prompt version hay khong.

    python scripts/check_prompt_trace.py            # 10 trace gan nhat
    python scripts/check_prompt_trace.py --limit 20

Dung sau moi lan doi LANGFUSE_PROMPT_LABEL va chay lai load_test: neu prompt
khong lay duoc tu Langfuse, app im lang fallback ve template local va trace van
tra ve 200 - chi metadata la sai. Script nay lam loi do hien ra.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

WIDTH = 78


def trace_url(host: str, trace: dict) -> str:
    """URL mo trace tren UI Langfuse.

    Bat buoc kem ?timestamp=: UI dung moc thoi gian de tim dung partition cua
    trace. Thieu tham so nay, trang trace bao "Trace not found" du trace van ton
    tai (GET /api/public/traces/{id} van tra ve 200).
    """
    project_id = trace.get("projectId")
    trace_id = trace.get("id", "")
    if not project_id:
        return trace_id
    url = f"{host}/project/{project_id}/traces/{trace_id}"
    timestamp = trace.get("timestamp")
    return f"{url}?timestamp={timestamp}" if timestamp else url


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="So trace gan nhat can xem")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = (os.getenv("LANGFUSE_HOST", "") or "").rstrip("/")
    if not (public_key and secret_key and host):
        print("Thieu LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST trong .env")
        return 1

    response = httpx.get(
        f"{host}/api/public/traces",
        auth=(public_key, secret_key),
        params={"limit": args.limit},
        timeout=30.0,
    )
    if response.status_code != 200:
        print(f"Goi Langfuse that bai: {response.status_code} {response.text[:200]}")
        return 1

    traces = response.json().get("data", [])

    print("=" * WIDTH)
    print("  KIEM TRA TRACE <-> PROMPT VERSION")
    print("=" * WIDTH)
    print(f"prompt      : {os.getenv('LANGFUSE_PROMPT_NAME', 'day13-chat')}")
    print(f"label .env  : {os.getenv('LANGFUSE_PROMPT_LABEL', 'production')}")
    print(f"{len(traces)} trace gan nhat:\n")

    combos: Counter[str] = Counter()
    for trace in traces:
        metadata = trace.get("metadata") or {}
        source = metadata.get("prompt_source", "?")
        version = metadata.get("prompt_version", "?")
        label = metadata.get("prompt_label", "?")
        combos[f"{source} / v{version} / {label}"] += 1
        flag = "OK " if source == "langfuse" else "SAI"
        print(f"  [{flag}] {trace.get('id')}")
        print(f"         source={source} version={version} label={label}")

    print("\n" + "-" * WIDTH)
    print("Tong hop:")
    for combo, count in combos.most_common():
        print(f"  {count:>3} trace | {combo}")

    broken = sum(count for combo, count in combos.items() if not combo.startswith("langfuse"))
    print("-" * WIDTH)
    if broken:
        print(f"CANH BAO: {broken}/{len(traces)} trace khong lay duoc prompt tu Langfuse.")
        print("Kiem tra: prompt name/label trong .env, da restart uvicorn chua,")
        print("va cache prompt 60s trong app/prompt_management.py.")
        return 1

    print(f"DAT: ca {len(traces)} trace deu gan prompt managed tu Langfuse.")
    if traces:
        print(f"\nMo trace de chup evidence:\n  {trace_url(host, traces[0])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
