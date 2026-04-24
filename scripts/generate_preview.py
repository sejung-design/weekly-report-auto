"""
GitHub Actions 실행용 — Notion '승인' 페이지를 감지해 HTML을 생성하고
GitHub Pages URL을 Notion 페이지에 자동 추가합니다.

환경변수:
  NOTION_API_KEY, NOTION_DATABASE_ID
  GITHUB_PAGES_BASE_URL  (예: https://sejung-design.github.io/weekly-report-auto)
"""
from __future__ import annotations

import html as html_lib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error, request


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "previews"


def require_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"환경변수 누락: {key}")
        sys.exit(1)
    return val


def notion_request(api_key, method, endpoint, body=None):
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
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        print(f"Notion API error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
        return None


def query_by_status(api_key, database_id, status):
    result = notion_request(api_key, "POST", f"/databases/{database_id}/query", {
        "filter": {"property": "상태", "select": {"equals": status}},
        "sorts": [{"property": "보고일", "direction": "descending"}],
        "page_size": 1,
    })
    results = (result or {}).get("results", [])
    return results[0] if results else None


def get_prop(page, name, ptype):
    prop = page.get("properties", {}).get(name, {})
    if ptype == "number":
        val = prop.get("number")
        return str(int(val)) if val is not None else ""
    if ptype == "date":
        return (prop.get("date") or {}).get("start", "")
    return ""


def plain_text(rt):
    return "".join(t.get("plain_text", "") for t in rt)


def fetch_blocks(api_key, block_id):
    result = notion_request(api_key, "GET", f"/blocks/{block_id}/children")
    return (result or {}).get("results", [])


def parse_blocks(api_key, page_id):
    blocks = fetch_blocks(api_key, page_id)
    s = {"summary_items": [], "task_rows": [], "next_plan_items": [], "issue_text": "없음", "note_text": ""}
    MAP = {
        "📌 이번 주 핵심 요약": "summary", "✅ 이번 주 주요 업무": "tasks",
        "🔜 다음 주 계획": "next_plan", "⚠️ 이슈 / 협조 요청": "issue", "💬 비고": "note",
    }
    cur = None
    for b in blocks:
        bt = b.get("type")
        if bt in ("heading_2", "heading_3"):
            cur = MAP.get(plain_text(b[bt]["rich_text"]))
        elif bt == "bulleted_list_item":
            txt = plain_text(b["bulleted_list_item"]["rich_text"])
            if cur == "summary": s["summary_items"].append(txt)
            elif cur == "next_plan": s["next_plan_items"].append(txt)
        elif bt == "table":
            rows = fetch_blocks(api_key, b["id"])
            for i, row in enumerate(rows):
                if i == 0: continue
                cells = row.get("table_row", {}).get("cells", [])
                if len(cells) >= 3:
                    s["task_rows"].append((plain_text(cells[0]), plain_text(cells[1]), plain_text(cells[2])))
        elif bt == "paragraph":
            txt = plain_text(b["paragraph"]["rich_text"])
            if cur == "issue" and txt: s["issue_text"] = txt
            elif cur == "note" and txt: s["note_text"] = txt
    return s


def build_html(page, api_key):
    week_num = get_prop(page, "주차", "number")
    week = f"W{int(float(week_num))}" if week_num else "W??"
    date_str = get_prop(page, "보고일", "date")
    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d")
        monday = report_date - timedelta(days=report_date.weekday())
        friday = monday + timedelta(days=4)
        date_range = f"{monday.month}.{monday.day}-{friday.month}.{friday.day}"
    except (ValueError, TypeError):
        date_range = date_str or ""

    yy = datetime.now().strftime("%y")
    subject = f"[Design Center] 주간업무보고 | {yy}년 {week} ({date_range})"
    s = parse_blocks(api_key, page["id"])

    def cell(text):
        return html_lib.escape(text).replace("\n", "<br>")

    summary_html = "".join(f"<li style='margin:0 0 6px 0'>{html_lib.escape(i)}</li>" for i in s["summary_items"])
    task_rows_html = "".join(
        f"<tr>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#555;vertical-align:top'>{cell(r[0])}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#222;vertical-align:top'>{cell(r[1])}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#0b6bcb;text-align:center;vertical-align:top;white-space:nowrap'>{cell(r[2])}</td>"
        f"</tr>" for r in s["task_rows"]
    )
    next_plan_html = "".join(f"<li style='margin:0 0 6px 0'>{html_lib.escape(i)}</li>" for i in s["next_plan_items"])

    summary_section = (
        f"<div style='padding:28px 28px 20px'>"
        f"<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>📌 이번 주 핵심 요약</h2>"
        f"<ul style='margin:0;padding-left:20px;color:#222;line-height:1.7'>{summary_html}</ul>"
        f"</div>"
    ) if s["summary_items"] else ""

    next_plan_section = (
        f"<div style='padding:0 28px 20px'>"
        f"<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>🔜 다음 주 계획</h2>"
        f"<ul style='margin:0;padding-left:20px;color:#222;line-height:1.7'>{next_plan_html}</ul>"
        f"</div>"
    ) if s["next_plan_items"] else ""

    note_section = (
        f"<div style='padding:0 28px 28px'>"
        f"<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>💬 비고</h2>"
        f"<p style='margin:0;color:#222;line-height:1.7'>{html_lib.escape(s['note_text'])}</p>"
        f"</div>"
    ) if s["note_text"] and s["note_text"] != "없음" else ""

    top_pad = "28px" if not s["summary_items"] else "0"

    body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{html_lib.escape(subject)}</title></head>
<body style="margin:0;padding:24px;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <p style="font-size:12px;color:#888;margin:0 0 12px 0;">
    ✂ 전체 선택(Ctrl+A 또는 ⌘A) → 복사 → Mailplug 붙여넣기 후 발송하세요.
  </p>
  <div style="max-width:760px;margin:0;background:#fff;border:2px solid #d0d0d0;border-radius:12px;overflow:hidden;">
    <div style="background:#18212f;padding:28px;color:#fff;">
      <div style="font-size:11px;letter-spacing:1.6px;color:#9eb0c9;">DESIGN CENTER</div>
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-end;margin-top:12px;">
        <div>
          <div style="font-size:24px;font-weight:700;">주간업무보고</div>
          <div style="font-size:13px;color:#d6deea;margin-top:6px;">{html_lib.escape(date_range)}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:22px;font-weight:700;">{html_lib.escape(week)}</div>
          <div style="font-size:12px;color:#d6deea;">{yy}년</div>
        </div>
      </div>
    </div>
    {summary_section}
    <div style="padding:{top_pad} 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">✅ 이번 주 주요 업무</h2>
      <table style="width:100%;border-collapse:collapse;border:1px solid #ececec;">
        <thead><tr style="background:#fafafa;">
          <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;width:20%">구분</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;">내용</th>
          <th style="padding:10px 12px;text-align:center;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;width:15%">상태</th>
        </tr></thead>
        <tbody>{task_rows_html}</tbody>
      </table>
    </div>
    {next_plan_section}
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">⚠️ 이슈 / 협조 요청</h2>
      <p style="margin:0;color:#222;line-height:1.7">{html_lib.escape(s['issue_text'])}</p>
    </div>
    {note_section}
  </div>
</body></html>"""

    return body, subject, week, date_str


def add_preview_link_to_notion(api_key, page_id, preview_url):
    """Notion 페이지 하단에 미리보기 링크를 추가합니다."""
    notion_request(api_key, "PATCH", f"/blocks/{page_id}/children", {
        "children": [
            {"type": "divider", "divider": {}},
            {
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": "📎 이메일 미리보기"}}]},
            },
            {"type": "bookmark", "bookmark": {"url": preview_url}},
        ]
    })


def update_notion_status(api_key, page_id, status):
    notion_request(api_key, "PATCH", f"/pages/{page_id}", {
        "properties": {"상태": {"select": {"name": status}}}
    })


def main():
    api_key = require_env("NOTION_API_KEY")
    db_id = require_env("NOTION_DATABASE_ID")
    pages_base = require_env("GITHUB_PAGES_BASE_URL").rstrip("/")

    page = query_by_status(api_key, db_id, "승인")
    if not page:
        print("승인 상태인 페이지가 없습니다. 종료합니다.")
        sys.exit(0)

    page_id = page["id"]
    print(f"승인 페이지 발견: {page_id}")

    html_content, subject, week, date_str = build_html(page, api_key)

    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = f"preview_{week}_{date_str}.html"
    out_path = OUTPUT_DIR / filename
    out_path.write_text(html_content, encoding="utf-8")
    print(f"HTML 생성: {filename}")

    preview_url = f"{pages_base}/previews/{filename}"
    print(f"미리보기 URL: {preview_url}")

    add_preview_link_to_notion(api_key, page_id, preview_url)
    print("Notion 페이지에 미리보기 링크 추가 완료")

    update_notion_status(api_key, page_id, "발송승인")
    print("Notion 상태 → 발송승인")

    # GitHub Actions에서 커밋할 파일명 출력
    print(f"OUTPUT_FILE={out_path}")


if __name__ == "__main__":
    main()
