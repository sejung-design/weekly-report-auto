"""
금요일 로컬 실행용 — Notion에서 '승인' 상태 보고서를 가져와 로컬 .md 파일로 복원합니다.
send_report.py가 읽을 수 있는 형식으로 저장합니다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib import error, request


BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "secrets.json"
LEGACY_CONFIG = BASE / "secrets.json"
REPORTS = BASE / "reports"

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def load_config():
    config_path = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def notion_request(api_key, method, endpoint, body=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    data = json.dumps(body).encode("utf-8") if body else None
    req = request.Request(
        f"{NOTION_API}{endpoint}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        print(f"Notion API error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
        return None


def query_approved(api_key, database_id):
    """상태=승인인 가장 최근 페이지를 가져옵니다."""
    body = {
        "filter": {
            "property": "상태",
            "select": {"equals": "승인"},
        },
        "sorts": [{"property": "보고일", "direction": "descending"}],
        "page_size": 1,
    }
    result = notion_request(api_key, "POST", f"/databases/{database_id}/query", body)
    if not result:
        return None
    results = result.get("results", [])
    return results[0] if results else None


def get_prop_text(page, prop_name) -> str:
    props = page.get("properties", {})
    prop = props.get(prop_name, {})
    prop_type = prop.get("type")
    if prop_type == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
    if prop_type == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    if prop_type == "number":
        val = prop.get("number")
        return str(int(val)) if val is not None else ""
    if prop_type == "date":
        return (prop.get("date") or {}).get("start", "")
    if prop_type == "select":
        return (prop.get("select") or {}).get("name", "")
    return ""


def reconstruct_md(page) -> tuple[str, str]:
    """Notion 페이지 속성에서 .md 파일 내용을 복원합니다."""
    week_num_str = get_prop_text(page, "주차")
    week_num = int(float(week_num_str)) if week_num_str else 0
    week = f"W{week_num}"
    date_str = get_prop_text(page, "보고일")
    summary = get_prop_text(page, "핵심요약")
    tasks = get_prop_text(page, "이번주업무")
    next_plan = get_prop_text(page, "다음주계획")
    issue = get_prop_text(page, "이슈협조") or "없음"
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    yy = datetime.now().strftime("%y")

    monday_str = date_str or datetime.now().strftime("%Y-%m-%d")
    try:
        monday = datetime.strptime(monday_str, "%Y-%m-%d")
        date_range = f"{monday.month}.{monday.day}-{monday.month}.{monday.day + 4}"
    except ValueError:
        date_range = monday_str

    content = f"""---
STATUS: APPROVED
WEEK: {week}
DATE_RANGE: {date_range}
CREATED: {created}
---

# [Design Center] 주간업무보고 | {yy}년 {week} ({date_range})

## 📌 이번 주 핵심 요약
{summary}

## ✅ 이번 주 주요 업무
{tasks}

## 🔜 다음 주 계획
{next_plan}

## ⚠️ 이슈 / 협조 요청
{issue}

## 💬 비고
"""
    filename = f"report_{week}_{monday_str}.md"
    return content, filename


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="파일을 저장하지 않고 내용만 출력합니다.")
    args = parser.parse_args()

    config = load_config()
    api_key = config["notion"]["api_key"]
    db_id = config["notion"]["database_id"]

    page = query_approved(api_key, db_id)
    if not page:
        print("승인된 보고서가 Notion에 없습니다. (상태=승인 항목을 찾지 못했습니다.)")
        sys.exit(1)

    page_id = page["id"]
    content, filename = reconstruct_md(page)

    if args.dry_run:
        print("DRY RUN: 파일을 저장하지 않습니다.")
        print(f"Notion Page ID: {page_id}")
        print(f"파일명: {filename}")
        print("--- 내용 미리보기 ---")
        print(content[:500])
        return

    REPORTS.mkdir(exist_ok=True)
    target = REPORTS / filename
    target.write_text(content, encoding="utf-8")
    print(f"Notion → 로컬 복원 완료: {target.name}")
    print(f"Notion Page ID: {page_id}")
    print(f"REPORT_PATH:{target}")
    print(f"NOTION_PAGE_ID:{page_id}")


if __name__ == "__main__":
    main()
