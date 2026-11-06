"""
GitHub Actions 실행용 — Notion '승인' 페이지를 감지해 HTML을 생성하고
GitHub Pages URL을 Notion 페이지에 자동 추가합니다.

환경변수:
  NOTION_API_KEY, NOTION_DATABASE_ID
  GITHUB_PAGES_BASE_URL  (예: https://sejung-design.github.io/weekly-report-auto)
"""
from __future__ import annotations

import html as html_lib
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error, request


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "previews"

# Copies only the report table; Ctrl+A also copies the page wrapper, which Outlook draws as grey lines.
COPY_SCRIPT = """<script>
(function () {
  var copying = false;
  document.addEventListener('copy', function (e) {
    if (!copying) return;
    var el = document.getElementById('report');
    e.clipboardData.setData('text/html', el.outerHTML);
    e.clipboardData.setData('text/plain', el.innerText);
    e.preventDefault();
  });
  document.getElementById('copy-btn').addEventListener('click', function () {
    copying = true;
    var ok = document.execCommand('copy');
    copying = false;
    document.getElementById('copy-msg').textContent = ok
      ? '복사됨! Mailplug 본문에 붙여넣기(Ctrl+V) 하세요.'
      : '복사 실패: Ctrl+A → Ctrl+C로 복사해 주세요.';
  });
})();
</script>"""


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
    s = {"summary_items": [], "task_rows": [], "next_plan_items": [], "issue_items": [], "note_items": []}
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
            elif cur in ("issue", "note") and txt: s[f"{cur}_items"].append((txt, True))
        elif bt == "table":
            rows = fetch_blocks(api_key, b["id"])
            for i, row in enumerate(rows):
                if i == 0: continue
                cells = row.get("table_row", {}).get("cells", [])
                if len(cells) >= 3:
                    s["task_rows"].append((plain_text(cells[0]), plain_text(cells[1]), plain_text(cells[2])))
        elif bt == "paragraph":
            txt = plain_text(b["paragraph"]["rich_text"])
            if cur in ("issue", "note") and txt: s[f"{cur}_items"].append((txt, False))
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
    F = "font-family:Noto Sans KR,-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;"
    TABLE_BODY_TEXT = f"font-size:11pt !important;line-height:1.45;mso-line-height-rule:exactly;{F}"
    COL_LINE = "border-right:1px solid #ececec;"
    task_rows_html = "".join(
        f"<tr>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;{COL_LINE}vertical-align:top;color:#555;{TABLE_BODY_TEXT}'><span style='color:#555;{TABLE_BODY_TEXT}'>{cell(r[0])}</span></td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;{COL_LINE}vertical-align:top;color:#222;{TABLE_BODY_TEXT}'><span style='color:#222;{TABLE_BODY_TEXT}'>{cell(r[1])}</span></td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;text-align:center;vertical-align:top;white-space:nowrap;color:#0b6bcb;{TABLE_BODY_TEXT}'><span style='color:#0b6bcb;{TABLE_BODY_TEXT}'>{cell(r[2])}</span></td>"
        f"</tr>" for r in s["task_rows"]
    )

    LIST_TEXT = f"font-size:11pt !important;line-height:1.7;mso-line-height-rule:exactly;{F}"

    def list_section(title, items, bottom_pad=20):
        rows = "".join(
            f"<tr><td style='padding:2px 0;color:#222;{LIST_TEXT}'><span style='color:#222;{LIST_TEXT}'>"
            f"{'&bull; ' if bullet else ''}{html_lib.escape(txt)}</span></td></tr>"
            for txt, bullet in items
        )
        return (
            f"<tr><td colspan='2' style='padding:0 28px {bottom_pad}px;background:#ffffff;'>"
            f"<p style='font-size:14px;margin:0 0 10px 0;color:#666;font-weight:bold;{F}'>{title}</p>"
            f"<table width='100%' cellpadding='0' cellspacing='0' border='0' style='border-collapse:collapse;'>{rows}</table>"
            f"</td></tr>"
        )

    next_plan_section = (
        list_section("🔜 다음 주 계획", [(i, True) for i in s["next_plan_items"]])
        if s["next_plan_items"] else ""
    )
    issue_section = list_section("&#x26a0;&#xfe0f; 이슈 / 협조 요청", s["issue_items"] or [("없음", False)])
    has_note = any(txt not in ("없음", "-") for txt, _ in s["note_items"])
    note_section = list_section("💬 비고", s["note_items"], bottom_pad=28) if has_note else ""

    body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{html_lib.escape(subject)}</title>
<style>@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap');</style>
</head>
<body style="margin:0;padding:24px;background:#ffffff;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
  <p style="font-size:12px;color:#888;margin:0 0 12px 0;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
    <button id="copy-btn" type="button" style="font-size:13px;font-weight:bold;padding:8px 16px;margin-right:8px;border:0;border-radius:6px;background:#18212f;color:#ffffff;cursor:pointer;">본문 복사</button>
    <span id="copy-msg">버튼을 누른 뒤 Mailplug 본문에 붙여넣기(Ctrl+V) 하세요.</span>
  </p>
  <div style="display:inline-block;border-radius:12px;overflow:hidden;">
  <table id="report" width="900" cellpadding="0" cellspacing="0" border="0" style="width:900px;border-collapse:collapse;">
    <tr><td style="border:2px solid #d0d0d0;padding:0;">
    <table width="900" cellpadding="0" cellspacing="0" border="0" style="width:900px;border-collapse:collapse;background:#ffffff;">
    <!-- 헤더: Outlook은 화면 배율에 따라 색 있는 행 경계에 흰 선을 그리므로 한 행으로 구성 -->
    <tr>
      <td bgcolor="#18212f" style="background-color:#18212f;padding:24px 0 24px 28px;vertical-align:top;">
        <div style="line-height:16px;mso-line-height-rule:exactly;font-size:11px;letter-spacing:1.6px;color:#9eb0c9;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">DESIGN CENTER</div>
        <div style="line-height:44px;mso-line-height-rule:exactly;font-size:24px;font-weight:bold;color:#ffffff;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">주간업무보고</div>
        <div style="line-height:22px;mso-line-height-rule:exactly;font-size:11pt;color:#d6deea;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">{html_lib.escape(date_range)}</div>
      </td>
      <td bgcolor="#18212f" width="100" style="background-color:#18212f;padding:24px 28px 24px 0;text-align:right;vertical-align:top;white-space:nowrap;width:100px;">
        <div style="line-height:16px;mso-line-height-rule:exactly;font-size:11px;">&nbsp;</div>
        <div style="line-height:44px;mso-line-height-rule:exactly;font-size:22px;font-weight:bold;color:#ffffff;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">{html_lib.escape(week)}</div>
        <div style="line-height:22px;mso-line-height-rule:exactly;font-size:12px;color:#d6deea;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">{yy}년</div>
      </td>
    </tr>
    <!-- 이번 주 주요 업무 -->
    <tr>
      <td colspan="2" style="padding:28px 28px 20px;background:#ffffff;">
        <p style="font-size:14px;margin:0 0 10px 0;color:#666;font-weight:bold;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">&#x2705; 이번 주 주요 업무</p>
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border:1px solid #ececec;">
          <tr bgcolor="#fafafa" style="background-color:#fafafa;">
            <th width="18%" style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;border-right:1px solid #ececec;color:#555;font-size:14px;font-weight:600;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">구분</th>
            <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;border-right:1px solid #ececec;color:#555;font-size:14px;font-weight:600;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">내용</th>
            <th width="70" style="padding:10px 12px;text-align:center;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">상태</th>
          </tr>
          {task_rows_html}
        </table>
      </td>
    </tr>
    {next_plan_section}
    {issue_section}
    {note_section}
    </table>
    </td></tr>
  </table>
  </div>
  {COPY_SCRIPT}
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


def finalize_preview(api_key, page_id, preview_url):
    add_preview_link_to_notion(api_key, page_id, preview_url)
    print("Notion preview link added")

    update_notion_status(api_key, page_id, '발송승인')
    print("Notion status updated")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true", help="Add a pushed preview URL to Notion.")
    parser.add_argument("--page-id", help="Notion page id to update when finalizing.")
    parser.add_argument("--preview-url", help="Preview URL to add when finalizing.")
    args = parser.parse_args()

    api_key = require_env("NOTION_API_KEY")
    if args.finalize:
        if not args.page_id or not args.preview_url:
            print("--finalize requires --page-id and --preview-url")
            sys.exit(1)
        finalize_preview(api_key, args.page_id, args.preview_url)
        return

    db_id = require_env("NOTION_DATABASE_ID")
    pages_base = require_env("GITHUB_PAGES_BASE_URL").rstrip("/")

    page = query_by_status(api_key, db_id, '승인')
    if not page:
        print("No approved page found. Exiting.")
        sys.exit(0)

    page_id = page["id"]
    print(f"Approved page found: {page_id}")

    html_content, subject, week, date_str = build_html(page, api_key)

    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = f"preview_{week}_{date_str}.html"
    out_path = OUTPUT_DIR / filename
    out_path.write_text(html_content, encoding="utf-8")
    print(f"HTML created: {filename}")

    preview_url = f"{pages_base}/previews/{filename}"
    print(f"Preview URL: {preview_url}")

    print(f"OUTPUT_FILE={out_path}")
    print(f"PAGE_ID={page_id}")
    print(f"PREVIEW_URL={preview_url}")

if __name__ == "__main__":
    main()
