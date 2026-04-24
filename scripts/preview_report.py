"""
금요일 실행용 — Notion 승인 보고서를 HTML로 렌더링해 브라우저로 엽니다.
브라우저에서 전체 선택(Ctrl+A) → 복사(Ctrl+C) → Mailplug에 붙여넣기(Ctrl+V)하면
테이블 서식이 그대로 유지됩니다.
"""
from __future__ import annotations

import html as html_lib
import json
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error, request


BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "secrets.json"
LEGACY_CONFIG = BASE / "secrets.json"

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
    body = {
        "filter": {"property": "상태", "select": {"equals": "승인"}},
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
    if prop_type == "number":
        val = prop.get("number")
        return str(int(val)) if val is not None else ""
    if prop_type == "date":
        return (prop.get("date") or {}).get("start", "")
    return ""


def plain_text(rich_text_list: list) -> str:
    return "".join(t.get("plain_text", "") for t in rich_text_list)


def fetch_blocks(api_key, block_id) -> list:
    result = notion_request(api_key, "GET", f"/blocks/{block_id}/children")
    return result.get("results", []) if result else []


def parse_page_blocks(api_key, page_id) -> dict:
    """페이지 본문 블록을 읽어 섹션별로 정리합니다."""
    blocks = fetch_blocks(api_key, page_id)

    sections = {
        "summary_items": [],
        "task_rows": [],
        "next_plan_items": [],
        "issue_text": "없음",
        "note_text": "",
    }

    SECTION_MAP = {
        "📌 이번 주 핵심 요약": "summary",
        "✅ 이번 주 주요 업무": "tasks",
        "🔜 다음 주 계획": "next_plan",
        "⚠️ 이슈 / 협조 요청": "issue",
        "💬 비고": "note",
    }

    current = None

    for block in blocks:
        btype = block.get("type")

        if btype in ("heading_2", "heading_3"):
            text = plain_text(block[btype]["rich_text"])
            current = SECTION_MAP.get(text)

        elif btype == "bulleted_list_item":
            text = plain_text(block["bulleted_list_item"]["rich_text"])
            if current == "summary":
                sections["summary_items"].append(text)
            elif current == "next_plan":
                sections["next_plan_items"].append(text)

        elif btype == "table":
            rows = fetch_blocks(api_key, block["id"])
            for i, row in enumerate(rows):
                if i == 0:  # 헤더 행 스킵
                    continue
                cells = row.get("table_row", {}).get("cells", [])
                if len(cells) >= 3:
                    sections["task_rows"].append((
                        plain_text(cells[0]),
                        plain_text(cells[1]),
                        plain_text(cells[2]),
                    ))

        elif btype == "paragraph":
            text = plain_text(block["paragraph"]["rich_text"])
            if current == "issue" and text:
                sections["issue_text"] = text
            elif current == "note" and text:
                sections["note_text"] = text

    return sections


def build_html(page, api_key) -> tuple[str, str]:
    week_num = get_prop_text(page, "주차")
    week = f"W{int(float(week_num))}" if week_num else "W??"
    date_str = get_prop_text(page, "보고일")

    try:
        report_date = datetime.strptime(date_str, "%Y-%m-%d")
        monday = report_date - timedelta(days=report_date.weekday())
        friday = monday + timedelta(days=4)
        date_range = f"{monday.month}.{monday.day}-{friday.month}.{friday.day}"
    except (ValueError, TypeError):
        date_range = date_str or ""

    yy = datetime.now().strftime("%y")
    subject = f"[Design Center] 주간업무보고 | {yy}년 {week} ({date_range})"

    sections = parse_page_blocks(api_key, page["id"])

    summary_html = "".join(
        f"<li style='margin:0 0 6px 0'>{html_lib.escape(item)}</li>"
        for item in sections["summary_items"]
    )
    def cell(text, color):
        return html_lib.escape(text).replace("\n", "<br>")

    task_rows_html = "".join(
        f"<tr>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#555;vertical-align:top'>{cell(r[0], '')}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#222;vertical-align:top'>{cell(r[1], '')}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#0b6bcb;text-align:center;vertical-align:top;white-space:nowrap'>{cell(r[2], '')}</td>"
        f"</tr>"
        for r in sections["task_rows"]
    )
    next_plan_html = "".join(
        f"<li style='margin:0 0 6px 0'>{html_lib.escape(item)}</li>"
        for item in sections["next_plan_items"]
    )

    summary_section = (
        f"<div style='padding:28px 28px 20px'>"
        f"<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>📌 이번 주 핵심 요약</h2>"
        f"<ul style='margin:0;padding-left:20px;color:#222;line-height:1.7'>{summary_html}</ul>"
        f"</div>"
    ) if sections["summary_items"] else ""

    next_plan_section = (
        f"<div style='padding:0 28px 20px'>"
        f"<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>🔜 다음 주 계획</h2>"
        f"<ul style='margin:0;padding-left:20px;color:#222;line-height:1.7'>{next_plan_html}</ul>"
        f"</div>"
    ) if sections["next_plan_items"] else ""

    note_section = (
        f"<div style='padding:0 28px 28px'>"
        f"<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>💬 비고</h2>"
        f"<p style='margin:0;color:#222;line-height:1.7'>{html_lib.escape(sections['note_text'])}</p>"
        f"</div>"
    ) if sections["note_text"] and sections["note_text"] != "없음" else ""

    body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{html_lib.escape(subject)}</title></head>
<body style="margin:0;padding:24px;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <p style="font-size:12px;color:#888;margin:0 0 12px 0;">
    ✂ 아래 내용을 전체 선택(Ctrl+A) → 복사(Ctrl+C) → Mailplug 본문에 붙여넣기(Ctrl+V) 하세요.
  </p>
  <div style="max-width:760px;margin:0;background:#ffffff;border:2px solid #d0d0d0;border-radius:12px;overflow:hidden;">
    <div style="background:#18212f;padding:28px;color:#ffffff;">
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
    <div style="padding:{'28px' if not sections['summary_items'] else '0'} 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">✅ 이번 주 주요 업무</h2>
      <table style="width:100%;border-collapse:collapse;border:1px solid #ececec;">
        <thead>
          <tr style="background:#fafafa;">
            <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;width:20%">구분</th>
            <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;">내용</th>
            <th style="padding:10px 12px;text-align:center;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;width:15%">상태</th>
          </tr>
        </thead>
        <tbody>{task_rows_html}</tbody>
      </table>
    </div>
    {next_plan_section}
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">⚠️ 이슈 / 협조 요청</h2>
      <p style="margin:0;color:#222;line-height:1.7">{html_lib.escape(sections['issue_text'])}</p>
    </div>
    {note_section}
  </div>
</body>
</html>"""

    return body, subject


def main():
    config = load_config()
    api_key = config["notion"]["api_key"]
    db_id = config["notion"]["database_id"]

    print("Notion에서 승인된 보고서를 가져오는 중...")
    page = query_approved(api_key, db_id)
    if not page:
        print("승인된 보고서가 없습니다. Notion에서 상태를 '승인'으로 변경해주세요.")
        sys.exit(1)

    html_content, subject = build_html(page, api_key)

    date_str = get_prop_text(page, "보고일") or datetime.now().strftime("%Y-%m-%d")
    week_num = get_prop_text(page, "주차")
    week = f"W{int(float(week_num))}" if week_num else "W0"
    out_path = BASE / "reports" / f"preview_{week}_{date_str}.html"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")

    print(f"HTML 생성 완료: {out_path.name}")
    print(f"제목: {subject}")
    print("브라우저가 열립니다. 전체 선택(Ctrl+A) → 복사(Ctrl+C) → Mailplug 붙여넣기(Ctrl+V)")

    webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    main()
