"""
목요일 16:00 클라우드 실행용 — 초안을 Notion에 직접 저장합니다.
페이지 본문에 서식 블록(제목/테이블/불릿)을 포함해 이메일 복사·붙여넣기에 적합한 형태로 저장합니다.
로컬 파일 의존 없이 독립 실행 가능합니다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
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


def monday_of_week(today: date) -> date:
    return today - timedelta(days=today.weekday())


def friday_of_week(today: date) -> date:
    return monday_of_week(today) + timedelta(days=4)


def week_label(today: date) -> str:
    return f"W{today.isocalendar().week}"


def date_range_label(today: date) -> str:
    monday = monday_of_week(today)
    friday = friday_of_week(today)
    return f"{monday.month}.{monday.day}-{friday.month}.{friday.day}"


def build_draft_sections(today: date) -> dict:
    week = week_label(today)
    date_range = date_range_label(today)
    yy = today.strftime("%y")

    summary_bullets = [
        "이번 주 핵심 내용 1",
        "이번 주 핵심 내용 2",
        "이번 주 핵심 내용 3",
    ]
    task_rows = [
        ("운영체계", "이번 주 주요 업무 내용을 입력하세요", "진행 중"),
        ("DLS 리서치", "이번 주 주요 업무 내용을 입력하세요", "진행 중"),
        ("협업 조율", "이번 주 주요 업무 내용을 입력하세요", "진행 중"),
    ]
    next_plan_bullets = [
        "다음 주 계획 1",
        "다음 주 계획 2",
        "다음 주 계획 3",
    ]

    summary_text = "\n".join(f"- {b}" for b in summary_bullets)
    tasks_text = (
        "| 구분 | 내용 | 상태 |\n"
        "|------|------|------|\n"
        + "\n".join(f"| {r[0]} | {r[1]} | {r[2]} |" for r in task_rows)
    )
    next_plan_text = "\n".join(f"- {b}" for b in next_plan_bullets)

    return {
        "week": week,
        "week_num": today.isocalendar().week,
        "date_range": date_range,
        "yy": yy,
        "summary": summary_text,
        "summary_bullets": summary_bullets,
        "tasks": tasks_text,
        "task_rows": task_rows,
        "next_plan": next_plan_text,
        "next_plan_bullets": next_plan_bullets,
        "issue": "없음",
    }


# ── Notion 블록 빌더 ──────────────────────────────────────────

def txt(content: str) -> dict:
    return {"type": "text", "text": {"content": content}}


def heading2(text: str) -> dict:
    return {"type": "heading_3", "heading_3": {"rich_text": [txt(text)]}}


def bullet(text: str) -> dict:
    return {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [txt(text)]}}


def paragraph(text: str) -> dict:
    return {"type": "paragraph", "paragraph": {"rich_text": [txt(text)]}}


def divider() -> dict:
    return {"type": "divider", "divider": {}}


def task_bullet(category: str, content: str, status: str) -> dict:
    return {
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [
                {"type": "text", "text": {"content": f"{category}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f"  {content}  "}},
                {"type": "text", "text": {"content": f"[{status}]"}, "annotations": {"color": "blue"}},
            ]
        },
    }


def table(rows: list[tuple[str, str, str]]) -> dict:
    def row_block(cells: tuple) -> dict:
        return {
            "type": "table_row",
            "table_row": {"cells": [[txt(c)] for c in cells]},
        }

    return {
        "type": "table",
        "table": {
            "table_width": 3,
            "has_column_header": True,
            "has_row_header": False,
            "children": [row_block(("구분", "내용", "상태"))] + [row_block(r) for r in rows],
        },
    }


def build_page_blocks(sections: dict, today: date) -> list:
    yy = sections["yy"]
    week = sections["week"]
    date_range = sections["date_range"]

    blocks = [
        # 보고서 제목 정보 (callout)
        {
            "type": "callout",
            "callout": {
                "rich_text": [txt(f"[Design Center] 주간업무보고 | {yy}년 {week} ({date_range})")],
                "icon": {"emoji": "📋"},
                "color": "gray_background",
            },
        },
        divider(),
        heading2("📌 이번 주 핵심 요약"),
        *[bullet(b) for b in sections["summary_bullets"]],
        divider(),
        heading2("✅ 이번 주 주요 업무"),
        table(sections["task_rows"]),
        divider(),
        heading2("🔜 다음 주 계획"),
        *[bullet(b) for b in sections["next_plan_bullets"]],
        divider(),
        heading2("⚠️ 이슈 / 협조 요청"),
        paragraph(sections["issue"]),
        divider(),
        heading2("💬 비고"),
        paragraph("필요 시 참고 메모를 입력하세요."),
    ]
    return blocks


# ── Notion API ────────────────────────────────────────────────

def notion_post(api_key, endpoint, body):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    req = request.Request(
        f"{NOTION_API}{endpoint}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        print(f"Notion API error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
        return None


def build_payload(config, sections, today: date):
    title = f"Design Center 주간업무보고 {sections['week']} ({sections['date_range']})"
    payload = {
        "parent": {"database_id": config["notion"]["database_id"]},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "주차": {"number": sections["week_num"]},
            "보고일": {"date": {"start": today.isoformat()}},
            "상태": {"select": {"name": "초안"}},
            "발송여부": {"checkbox": False},
        },
        "children": build_page_blocks(sections, today),
    }
    return payload, title


# ── 로컬 백업 ─────────────────────────────────────────────────

def save_local_backup(sections, today: date) -> Path:
    REPORTS.mkdir(exist_ok=True)
    filename = f"report_{sections['week']}_{today.isoformat()}.md"
    target = REPORTS / filename
    content = (
        f"---\nSTATUS: DRAFT\nWEEK: {sections['week']}\n"
        f"DATE_RANGE: {sections['date_range']}\n"
        f"CREATED: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n---\n\n"
        f"# [Design Center] 주간업무보고 | {sections['yy']}년 {sections['week']} ({sections['date_range']})\n\n"
        f"## 📌 이번 주 핵심 요약\n{sections['summary']}\n\n"
        f"## ✅ 이번 주 주요 업무\n{sections['tasks']}\n\n"
        f"## 🔜 다음 주 계획\n{sections['next_plan']}\n\n"
        f"## ⚠️ 이슈 / 협조 요청\n{sections['issue']}\n\n"
        f"## 💬 비고\n필요 시 참고 메모를 입력하세요.\n"
    )
    target.write_text(content, encoding="utf-8")
    return target


# ── main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="기준 날짜(YYYY-MM-DD). 기본값은 오늘.")
    parser.add_argument("--no-local", action="store_true", help="로컬 백업 파일을 저장하지 않습니다.")
    parser.add_argument("--dry-run", action="store_true", help="Notion에 실제로 저장하지 않습니다.")
    args = parser.parse_args()

    today = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    sections = build_draft_sections(today)

    print(f"Draft: {sections['week']} ({sections['date_range']})")

    config = load_config()
    payload, title = build_payload(config, sections, today)

    if args.dry_run:
        print("DRY RUN: Notion 저장을 건너뜁니다.")
        print(f"Title: {title}")
        print(f"Page blocks: {len(payload['children'])}개")
        return

    result = notion_post(config["notion"]["api_key"], "/pages", payload)
    if result and result.get("id"):
        print(f"Notion 초안 저장 완료: {title}")
        print(f"Page ID: {result['id']}")
        if result.get("url"):
            print(f"URL: {result['url']}")
    else:
        print("Notion 저장 실패.")
        sys.exit(1)

    if not args.no_local:
        local_path = save_local_backup(sections, today)
        print(f"로컬 백업: {local_path.name}")


if __name__ == "__main__":
    main()
