"""
금요일 전체 흐름 — Notion 승인 보고서 → 메일 발송 → Notion 상태 업데이트.
컴퓨터에서 한 번만 실행하면 됩니다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib import error, request


BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config" / "secrets.json"
LEGACY_CONFIG = BASE / "secrets.json"
SCRIPTS = BASE / "scripts"

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def load_config():
    config_path = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def notion_patch(api_key, page_id, body):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    req = request.Request(
        f"{NOTION_API}/pages/{page_id}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        print(f"Notion PATCH error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
        return None


def run(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode, result.stdout


def parse_output_value(output: str, key: str) -> str:
    for line in output.splitlines():
        if line.startswith(f"{key}:"):
            return line[len(key) + 1:].strip()
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute-send",
        action="store_true",
        help="실제 메일을 발송합니다. 없으면 dry-run만 수행합니다.",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("금요일 보고서 발송 흐름 시작")
    print("=" * 50)

    # 1단계: Notion에서 승인된 보고서 가져오기
    print("\n[1/4] Notion에서 승인된 보고서 가져오는 중...")
    code, output = run([sys.executable, str(SCRIPTS / "fetch_from_notion.py")])
    if code != 0:
        print("중단: Notion에서 보고서를 가져오지 못했습니다.")
        sys.exit(1)

    report_path = parse_output_value(output, "REPORT_PATH")
    notion_page_id = parse_output_value(output, "NOTION_PAGE_ID")

    if not report_path:
        print("중단: 복원된 파일 경로를 찾지 못했습니다.")
        sys.exit(1)

    print(f"  보고서: {Path(report_path).name}")
    print(f"  Notion Page ID: {notion_page_id}")

    # 2단계: dry-run 검증
    print("\n[2/4] 발송 전 dry-run 검증 중...")
    code, _ = run([sys.executable, str(SCRIPTS / "send_report.py"), "--dry-run", "--report", report_path])
    if code != 0:
        print("중단: dry-run 실패. 실제 발송을 진행하지 않습니다.")
        sys.exit(1)
    print("  dry-run 통과.")

    if not args.execute_send:
        print("\ndry-run만 완료했습니다.")
        print("실제 발송하려면: python scripts/run_friday_from_notion.py --execute-send")
        return

    # 3단계: 실제 메일 발송
    print("\n[3/4] 메일 발송 중...")
    code, _ = run([sys.executable, str(SCRIPTS / "send_report.py"), "--report", report_path])
    if code != 0:
        print("중단: 메일 발송 실패. Notion 상태를 변경하지 않습니다.")
        sys.exit(1)
    print("  메일 발송 완료.")

    # 4단계: Notion 상태 업데이트
    print("\n[4/4] Notion 상태 업데이트 중...")
    if notion_page_id:
        config = load_config()
        result = notion_patch(
            config["notion"]["api_key"],
            notion_page_id,
            {
                "properties": {
                    "상태": {"select": {"name": "발송완료"}},
                    "발송여부": {"checkbox": True},
                    "발송시각": {"date": {"start": datetime.now().isoformat()}},
                }
            },
        )
        if result:
            print("  Notion 상태 → 발송완료")
        else:
            print("  경고: Notion 상태 업데이트 실패. 수동으로 확인하세요.")
    else:
        print("  경고: Notion Page ID 없음. 상태 업데이트를 건너뜁니다.")

    print("\n" + "=" * 50)
    print("완료: 발송 및 Notion 업데이트가 모두 끝났습니다.")
    print("=" * 50)


if __name__ == "__main__":
    main()
