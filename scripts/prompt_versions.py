"""Quản lý prompt `day13-chat` trong project Langfuse cá nhân.

    python scripts/prompt_versions.py create             # tạo v1 (baseline, production) và v2 (candidate)
    python scripts/prompt_versions.py status             # liệt kê version và label hiện tại
    python scripts/prompt_versions.py promote --version 2  # chuyển label production sang v2
    python scripts/prompt_versions.py promote --version 1  # rollback production về v1

Script đọc key từ `.env`; không in key ra màn hình.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

# Hai version chỉ khác nhau một dòng hướng dẫn format; cả hai giữ đủ ba biến bắt buộc.
PROMPT_V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
PROMPT_V2 = PROMPT_V1 + "\nAnswer in at most 3 short sentences and cite the docs you used."
MAX_VERSIONS_TO_LIST = 20


def _client():
    from langfuse import get_client

    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        print("Thiếu LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY trong .env")
        raise SystemExit(1)
    return get_client()


def _get_version(client, name: str, version: int):
    try:
        return client.get_prompt(
            name, version=version, cache_ttl_seconds=0, max_retries=2, fetch_timeout_seconds=10
        )
    except Exception as exc:
        # Only a 404 means "this version does not exist"; anything else (timeout, auth)
        # must stop the script instead of being reported as a missing prompt.
        if getattr(exc, "status_code", None) == 404 or type(exc).__name__ == "NotFoundError":
            return None
        print(f"Lỗi khi gọi Langfuse ({type(exc).__name__}): {exc}")
        raise SystemExit(1) from exc


def create(client, name: str) -> None:
    if _get_version(client, name, 1) is not None:
        print(f"Prompt '{name}' đã tồn tại; không tạo thêm version. Dùng 'status' để xem.")
        raise SystemExit(1)
    v1 = client.create_prompt(
        name=name,
        prompt=PROMPT_V1,
        labels=["baseline", "production"],
        type="text",
        commit_message="v1: baseline prompt",
    )
    v2 = client.create_prompt(
        name=name,
        prompt=PROMPT_V2,
        labels=["candidate"],
        type="text",
        commit_message="v2: limit answer length and cite docs",
    )
    print(f"Đã tạo {name} v{v1.version} (baseline, production) và v{v2.version} (candidate).")


def status(client, name: str) -> None:
    found = False
    for version in range(1, MAX_VERSIONS_TO_LIST + 1):
        prompt = _get_version(client, name, version)
        if prompt is None:
            break
        found = True
        labels = ", ".join(sorted(prompt.labels)) or "-"
        last_line = prompt.prompt.splitlines()[-1]
        print(f"v{prompt.version}: labels=[{labels}] | dòng cuối: {last_line}")
    if not found:
        print(f"Chưa có prompt '{name}'. Chạy 'create' trước.")


def promote(client, name: str, version: int) -> None:
    prompt = _get_version(client, name, version)
    if prompt is None:
        print(f"Không tìm thấy {name} v{version}.")
        raise SystemExit(1)
    # Giữ các label sẵn có của version đó và thêm production; Langfuse tự gỡ
    # production khỏi version cũ vì label là duy nhất giữa các version.
    new_labels = sorted((set(prompt.labels) | {"production"}) - {"latest"})
    client.update_prompt(name=name, version=version, new_labels=new_labels)
    print(f"Label production giờ trỏ tới {name} v{version}.")
    print("App cache prompt 60 giây: đợi 1 phút hoặc restart API trước khi chạy lại request.")


def main() -> None:
    configure_utf8_stdio()
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description="Quản lý prompt version trên Langfuse")
    parser.add_argument("command", choices=["create", "status", "promote"])
    parser.add_argument("--version", type=int, help="Version nhận label production (dùng với promote)")
    args = parser.parse_args()

    name = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    client = _client()
    if args.command == "create":
        create(client, name)
    elif args.command == "status":
        status(client, name)
    else:
        if args.version is None:
            parser.error("promote cần --version")
        promote(client, name, args.version)
    client.flush()


if __name__ == "__main__":
    main()
