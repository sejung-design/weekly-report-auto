from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib import error, request


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = os.environ.get("NOTION_VERSION", "2025-09-03")
SEOUL = timezone(timedelta(hours=9))


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"Missing environment variable: {name}")
        sys.exit(1)
    return value


def notion_request(api_key: str, method: str, endpoint: str, body: dict | None = None) -> dict | None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = request.Request(
        f"{NOTION_API}{endpoint}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        print(f"Notion API error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
        return None
    except error.URLError as exc:
        print(f"Notion request failed: {exc}")
        return None


def monday_of_week(today):
    return today - timedelta(days=today.weekday())


def friday_of_week(today):
    return monday_of_week(today) + timedelta(days=4)


def date_range_label(today) -> str:
    monday = monday_of_week(today)
    friday = friday_of_week(today)
    return f"{monday.month}.{monday.day}-{friday.month}.{friday.day}"


def report_meta(today):
    week_num = today.isocalendar().week
    week = f"W{week_num}"
    date_range = date_range_label(today)
    yy = today.strftime("%y")
    title = f"Design Center 주간업무보고 {week} ({date_range})"
    return {
        "week": week,
        "week_num": week_num,
        "date_range": date_range,
        "yy": yy,
        "today": today.isoformat(),
        "title": title,
    }


def load_draft(path: str | None) -> dict:
    if path:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    raw = os.environ.get("DRAFT_JSON", "").strip()
    if raw:
        return json.loads(raw)

    return {
        "tasks": [
            {"category": "운영체계", "content": "주요 업무 내용을 입력하세요", "status": "진행 중"},
            {"category": "DLS 리서치", "content": "주요 업무 내용을 입력하세요", "status": "진행 중"},
            {"category": "협업", "content": "주요 업무 내용을 입력하세요", "status": "진행 중"},
            {"category": "기타", "content": "주요 업무 내용을 입력하세요", "status": "진행 중"},
        ],
        "next_plan": ["다음 주 계획 1", "다음 주 계획 2", "다음 주 계획 3"],
        "issue": "없음",
        "note": "-",
    }


def normalize_draft(draft: dict) -> dict:
    tasks = draft.get("tasks") or []
    normalized_tasks = []
    for task in tasks[:4]:
        normalized_tasks.append({
            "category": str(task.get("category", "")).strip() or "기타",
            "content": str(task.get("content", "")).strip() or "주요 업무 내용",
            "status": str(task.get("status", "")).strip() or "진행 중",
        })

    while len(normalized_tasks) < 4:
        defaults = ["운영체계", "DLS 리서치", "협업", "기타"]
        idx = len(normalized_tasks)
        normalized_tasks.append({
            "category": defaults[idx],
            "content": "주요 업무 내용",
            "status": "진행 중",
        })

    next_plan = [str(item).strip() for item in (draft.get("next_plan") or []) if str(item).strip()]
    while len(next_plan) < 3:
        next_plan.append(f"다음 주 계획 {len(next_plan) + 1}")

    return {
        "tasks": normalized_tasks[:4],
        "next_plan": next_plan[:3],
        "issue": str(draft.get("issue", "없음")).strip() or "없음",
        "note": str(draft.get("note", "-")).strip() or "-",
    }


def text(content: str, *, bold: bool = False) -> dict:
    item = {"type": "text", "text": {"content": content}}
    if bold:
        item["annotations"] = {"bold": True}
    return item


def paragraph(content: str) -> dict:
    return {"type": "paragraph", "paragraph": {"rich_text": [text(content)]}}


def heading_2(content: str) -> dict:
    return {"type": "heading_2", "heading_2": {"rich_text": [text(content)]}}


def bullet(content: str) -> dict:
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [text(content)]}}


def table_row(cells: list[str]) -> dict:
    return {
        "type": "table_row",
        "table_row": {
            "cells": [[text(cell)] for cell in cells],
        },
    }


def task_table(tasks: list[dict]) -> dict:
    rows = [table_row(["구분", "내용", "상태"])]
    rows.extend(table_row([task["category"], task["content"], task["status"]]) for task in tasks)
    return {
        "type": "table",
        "table": {
            "table_width": 3,
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    }


def page_children(meta: dict, draft: dict) -> list[dict]:
    return [
        {
            "type": "quote",
            "quote": {
                "rich_text": [
                    text(f"📋 Design Center 주간업무보고 {meta['week']} ({meta['date_range']})", bold=True),
                    text(f"\n보고일: {meta['today']} | 작성: Design Center | 상태: 초안"),
                ],
            },
        },
        paragraph(""),
        heading_2("✅ 이번 주 주요 업무"),
        task_table(draft["tasks"]),
        heading_2("🔜 다음 주 계획"),
        *[bullet(item) for item in draft["next_plan"]],
        heading_2("⚠️ 이슈 / 협조 요청"),
        paragraph(draft["issue"]),
        heading_2("💬 비고"),
        paragraph(draft["note"]),
    ]


def schema_properties(api_key: str, data_source_id: str) -> dict:
    schema = notion_request(api_key, "GET", f"/data_sources/{data_source_id}")
    return (schema or {}).get("properties", {})


def property_if_present(properties: dict, name: str, value: dict) -> tuple[str, dict] | None:
    if name not in properties:
        return None
    return name, value


def build_properties(schema: dict, meta: dict) -> dict:
    candidates = [
        property_if_present(schema, "제목", {"title": [{"text": {"content": meta["title"]}}]}),
        property_if_present(schema, "주차", {"number": meta["week_num"]}),
        property_if_present(schema, "보고일", {"date": {"start": meta["today"]}}),
        property_if_present(schema, "상태", {"select": {"name": "초안"}}),
        property_if_present(schema, "발송여부", {"checkbox": False}),
    ]
    return {name: value for item in candidates if item for name, value in [item]}


def default_schema() -> dict:
    return {
        "제목": {"type": "title"},
        "주차": {"type": "number"},
        "보고일": {"type": "date"},
        "상태": {"type": "select"},
        "발송여부": {"type": "checkbox"},
    }


def existing_page(api_key: str, data_source_id: str, title: str) -> dict | None:
    body = {
        "filter": {
            "property": "제목",
            "title": {"equals": title},
        },
        "page_size": 1,
    }
    result = notion_request(api_key, "POST", f"/data_sources/{data_source_id}/query", body)
    results = (result or {}).get("results", [])
    return results[0] if results else None


def create_page(api_key: str, data_source_id: str, properties: dict, children: list[dict]) -> dict | None:
    return notion_request(api_key, "POST", "/pages", {
        "parent": {"data_source_id": data_source_id},
        "properties": properties,
        "children": children,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-json", help="JSON file containing AI-generated tasks and plans.")
    parser.add_argument("--date", help="Override date in YYYY-MM-DD. Defaults to today in Asia/Seoul.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-duplicate", action="store_true")
    args = parser.parse_args()

    today = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now(SEOUL).date()
    )
    meta = report_meta(today)
    draft = normalize_draft(load_draft(args.draft_json))

    api_key = os.environ.get("NOTION_API_KEY", "").strip()
    data_source_id = os.environ.get("NOTION_DATA_SOURCE_ID", "").strip()
    if args.dry_run and (not api_key or not data_source_id):
        schema = default_schema()
    else:
        api_key = require_env("NOTION_API_KEY")
        data_source_id = require_env("NOTION_DATA_SOURCE_ID")
        schema = schema_properties(api_key, data_source_id)
    properties = build_properties(schema, meta)
    children = page_children(meta, draft)

    if "제목" not in properties:
        print("Notion data source must contain a title property named '제목'.")
        sys.exit(1)

    if args.dry_run:
        print(f"DRY RUN: {meta['title']}")
        print(f"Properties: {', '.join(properties.keys())}")
        print(f"Tasks: {len(draft['tasks'])}")
        print(f"Next plans: {len(draft['next_plan'])}")
        return

    if not args.allow_duplicate:
        existing = existing_page(api_key, data_source_id, meta["title"])
        if existing:
            print(f"초안 저장 완료: {meta['title']}")
            print(f"Already exists: {existing.get('url', existing.get('id'))}")
            return

    page = create_page(api_key, data_source_id, properties, children)
    if not page or not page.get("id"):
        print("Notion draft creation failed.")
        sys.exit(1)

    print(f"초안 저장 완료: {meta['title']}")
    if page.get("url"):
        print(page["url"])


if __name__ == "__main__":
    main()
