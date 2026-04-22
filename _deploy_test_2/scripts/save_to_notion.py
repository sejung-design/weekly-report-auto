import json, re, sys, requests
from pathlib import Path
from datetime import datetime

BASE = Path("C:/DesignCenter")
CONFIG = BASE / "config" / "secrets.json"
REPORTS = BASE / "reports"
ARCHIVE = BASE / "archive"

def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)

def find_sent_report():
    for f in sorted(REPORTS.glob("report_W*.md"), reverse=True):
        content = f.read_text(encoding="utf-8")
        if "STATUS: SENT" in content:
            return f, content
    return None, None

def parse_report(content):
    def section(title):
        if title in content:
            return content.split(title)[1].split("##")[0].strip()
        return ""
    week = re.search(r'WEEK:\s*(W\d+)', content)
    week_num_match = re.search(r'W(\d+)', week.group(1)) if week else None
    date_range = re.search(r'DATE_RANGE:\s*(.+)', content)
    summary_raw = section("## 📌 핵심 요약")
    summary_lines = [l.lstrip("- ").strip() for l in summary_raw.split("\n") if l.strip().startswith("-")]
    issue_raw = section("## ⚠️ 이슈 / 협조 요청") or section("## ⚠️")
    return {
        "week": week.group(1) if week else "W??",
        "week_num": int(week_num_match.group(1)) if week_num_match else 0,
        "date_range": date_range.group(1).strip() if date_range else "",
        "summary": "\n".join(summary_lines),
        "tasks": section("## ✅ 이번 주 주요 업무"),
        "next_plan": section("## 🔜 다음 주 계획"),
        "issue": issue_raw if issue_raw else "없음",
        "sent_at": datetime.now().isoformat()
    }

def save_to_notion(config, data):
    headers = {
        "Authorization": f"Bearer {config['notion']['api_key']}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    title = f"Design Center 주간보고 {data['week']} ({data['date_range']})"
    payload = {
        "parent": {"database_id": config["notion"]["database_id"]},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "주차": {"number": data["week_num"]},
            "보고일": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
            "핵심요약": {"rich_text": [{"text": {"content": data["summary"][:2000]}}]},
            "이번주업무": {"rich_text": [{"text": {"content": data["tasks"][:2000]}}]},
            "다음주계획": {"rich_text": [{"text": {"content": data["next_plan"][:2000]}}]},
            "이슈협조": {"rich_text": [{"text": {"content": data["issue"][:2000]}}]},
            "발송여부": {"checkbox": True},
            "발송시각": {"date": {"start": data["sent_at"]}}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
    if res.status_code == 200:
        print(f"✅ Notion 저장 완료: {title}")
        return True
    else:
        print(f"❌ Notion 저장 실패: {res.status_code} — {res.text}")
        return False

def main():
    config = load_config()
    filepath, content = find_sent_report()
    if not filepath:
        print("❌ SENT 보고서 없음.")
        sys.exit(1)
    data = parse_report(content)
    if save_to_notion(config, data):
        ARCHIVE.mkdir(exist_ok=True)
        filepath.rename(ARCHIVE / filepath.name)
        print(f"✅ 아카이브 완료: {filepath.name}")
    else:
        print("⚠️ Notion 저장 실패. 수동 저장 필요.")
        sys.exit(1)

if __name__ == "__main__":
    main()
