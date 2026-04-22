"""
GitHub Actions 클라우드 실행용 — Notion '발송승인' 보고서를 자동 발송합니다.
환경변수에서 인증 정보를 읽으므로 로컬 secrets.json 없이도 동작합니다.

환경변수:
  NOTION_API_KEY, NOTION_DATABASE_ID
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
  RECIPIENTS (쉼표 구분), CC (쉼표 구분, 선택)
  SENDER_NAME (선택, 기본값 "Design Center")
  TEST_MODE (true면 본인에게만 발송)
"""
from __future__ import annotations

import html as html_lib
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib import error, request


NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# ── 환경변수 ──────────────────────────────────────────────────

def require_env(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        print(f"환경변수 누락: {key}")
        sys.exit(1)
    return val


def load_config() -> dict:
    return {
        "notion_api_key": require_env("NOTION_API_KEY"),
        "database_id": require_env("NOTION_DATABASE_ID"),
        "smtp": {
            "host": require_env("SMTP_HOST"),
            "port": int(require_env("SMTP_PORT")),
            "user": require_env("SMTP_USER"),
            "password": require_env("SMTP_PASSWORD"),
        },
        "recipients": [r.strip() for r in require_env("RECIPIENTS").split(",")],
        "cc": [c.strip() for c in os.environ.get("CC", "").split(",") if c.strip()],
        "sender_name": os.environ.get("SENDER_NAME", "Design Center"),
        "test_mode": os.environ.get("TEST_MODE", "false").lower() == "true",
    }


# ── Notion API ────────────────────────────────────────────────

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


def query_by_status(api_key, database_id, status: str):
    body = {
        "filter": {"property": "상태", "select": {"equals": status}},
        "sorts": [{"property": "보고일", "direction": "descending"}],
        "page_size": 1,
    }
    result = notion_request(api_key, "POST", f"/databases/{database_id}/query", body)
    if not result:
        return None
    results = result.get("results", [])
    return results[0] if results else None


def get_prop(page, prop_name, prop_type) -> str:
    prop = page.get("properties", {}).get(prop_name, {})
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
            current = SECTION_MAP.get(plain_text(block[btype]["rich_text"]))
        elif btype == "bulleted_list_item":
            text = plain_text(block["bulleted_list_item"]["rich_text"])
            if current == "summary":
                sections["summary_items"].append(text)
            elif current == "next_plan":
                sections["next_plan_items"].append(text)
        elif btype == "table":
            rows = fetch_blocks(api_key, block["id"])
            for i, row in enumerate(rows):
                if i == 0:
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


# ── HTML 빌더 ─────────────────────────────────────────────────

def build_html(page, api_key) -> tuple[str, str]:
    week_num = get_prop(page, "주차", "number")
    week = f"W{int(float(week_num))}" if week_num else "W??"
    date_str = get_prop(page, "보고일", "date")
    try:
        monday = datetime.strptime(date_str, "%Y-%m-%d")
        date_range = f"{monday.month}.{monday.day}-{monday.month}.{monday.day + 4}"
    except (ValueError, TypeError):
        date_range = date_str or ""

    yy = datetime.now().strftime("%y")
    subject = f"[Design Center] 주간업무보고 | {yy}년 {week} ({date_range})"
    s = parse_page_blocks(api_key, page["id"])

    summary_html = "".join(f"<li style='margin:0 0 6px 0'>{html_lib.escape(i)}</li>" for i in s["summary_items"])
    task_rows_html = "".join(
        f"<tr>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#555'>{html_lib.escape(r[0])}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#222'>{html_lib.escape(r[1])}</td>"
        f"<td style='padding:10px 12px;border-bottom:1px solid #ececec;color:#0b6bcb;text-align:center'>{html_lib.escape(r[2])}</td>"
        f"</tr>"
        for r in s["task_rows"]
    )
    next_plan_html = "".join(f"<li style='margin:0 0 6px 0'>{html_lib.escape(i)}</li>" for i in s["next_plan_items"])
    note_html = (
        f"<div style='padding:0 28px 28px'>"
        f"<h2 style='font-size:14px;margin:0 0 10px 0;color:#666'>💬 비고</h2>"
        f"<p style='margin:0;color:#222;line-height:1.7'>{html_lib.escape(s['note_text'])}</p>"
        f"</div>"
    ) if s["note_text"] else ""

    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:24px;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:760px;margin:0;background:#ffffff;border:1px solid #e8e8e8;border-radius:12px;overflow:hidden;">
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
    <div style="padding:28px 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">📌 이번 주 핵심 요약</h2>
      <ul style="margin:0;padding-left:20px;color:#222;line-height:1.7">{summary_html}</ul>
    </div>
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">✅ 이번 주 주요 업무</h2>
      <table style="width:100%;border-collapse:collapse;border:1px solid #ececec;">
        <thead><tr style="background:#fafafa;">
          <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;">구분</th>
          <th style="padding:10px 12px;text-align:left;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;">내용</th>
          <th style="padding:10px 12px;text-align:center;border-bottom:1px solid #ececec;color:#555;font-size:14px;font-weight:600;">상태</th>
        </tr></thead>
        <tbody>{task_rows_html}</tbody>
      </table>
    </div>
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">🔜 다음 주 계획</h2>
      <ul style="margin:0;padding-left:20px;color:#222;line-height:1.7">{next_plan_html}</ul>
    </div>
    <div style="padding:0 28px 20px">
      <h2 style="font-size:14px;margin:0 0 10px 0;color:#666">⚠️ 이슈 / 협조 요청</h2>
      <p style="margin:0;color:#222;line-height:1.7">{html_lib.escape(s['issue_text'])}</p>
    </div>
    {note_html}
  </div>
</body></html>"""

    return html_body, subject


# ── 이메일 발송 ───────────────────────────────────────────────

def send_email(config, html_body, subject):
    smtp = config["smtp"]
    recipients = [smtp["user"]] if config["test_mode"] else config["recipients"]
    cc = [] if config["test_mode"] else config["cc"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{config['sender_name']} <{smtp['user']}>"
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    all_recipients = recipients + cc
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp["host"], smtp["port"], context=ctx) as server:
        server.login(smtp["user"], smtp["password"])
        server.sendmail(smtp["user"], all_recipients, msg.as_string())

    mode = "테스트 " if config["test_mode"] else ""
    print(f"{mode}이메일 발송 완료 → {', '.join(recipients)}")


# ── Notion 상태 업데이트 ──────────────────────────────────────

def update_status(api_key, page_id):
    notion_request(api_key, "PATCH", f"/pages/{page_id}", {
        "properties": {
            "상태": {"select": {"name": "발송완료"}},
            "발송여부": {"checkbox": True},
        }
    })
    print("Notion 상태 → 발송완료")


# ── main ──────────────────────────────────────────────────────

def main():
    config = load_config()
    api_key = config["notion_api_key"]
    db_id = config["database_id"]

    if config["test_mode"]:
        print("테스트 모드: 본인 이메일로만 발송합니다.")

    page = query_by_status(api_key, db_id, "발송승인")
    if not page:
        print("발송승인 상태인 보고서가 없습니다. 종료합니다.")
        sys.exit(0)

    page_id = page["id"]
    print(f"발송 대상 페이지: {page_id}")

    html_body, subject = build_html(page, api_key)
    print(f"제목: {subject}")

    send_email(config, html_body, subject)
    update_status(api_key, page_id)


if __name__ == "__main__":
    main()
