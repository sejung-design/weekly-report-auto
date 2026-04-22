import argparse
import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent.parent
SEND_SCRIPT = BASE / "scripts" / "send_report.py"
NOTION_SCRIPT = BASE / "scripts" / "save_to_notion.py"


def run_command(command):
    result = subprocess.run(command, cwd=BASE, text=True)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", help="Report path to use for both steps.")
    parser.add_argument(
        "--execute-send",
        action="store_true",
        help="Actually send the email after the dry-run succeeds.",
    )
    parser.add_argument(
        "--skip-notion",
        action="store_true",
        help="Skip the Notion save step.",
    )
    args = parser.parse_args()

    dry_run_command = [sys.executable, str(SEND_SCRIPT), "--dry-run"]
    if args.report:
        dry_run_command.extend(["--report", args.report])
    print("Step 1/3: send dry-run")
    run_command(dry_run_command)

    if not args.execute_send:
        print("Stopped after dry-run. Re-run with --execute-send to send the email.")
        return

    send_command = [sys.executable, str(SEND_SCRIPT)]
    if args.report:
        send_command.extend(["--report", args.report])
    print("Step 2/3: actual send")
    run_command(send_command)

    if args.skip_notion:
        print("Notion save skipped by option.")
        return

    notion_command = [sys.executable, str(NOTION_SCRIPT)]
    if args.report:
        notion_command.extend(["--report", args.report])
    print("Step 3/3: save to Notion")
    run_command(notion_command)


if __name__ == "__main__":
    main()
