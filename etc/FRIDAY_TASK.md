# 금요일 발송 흐름 — 로컬 실행

목요일에 Notion에 저장된 초안을 검토 후 승인하면, 아래 명령으로 메일 발송까지 완료됩니다.

---

## 전제 조건

Notion 앱(아이폰 또는 PC)에서 해당 주 보고서의 **상태를 "승인"으로 변경**한 뒤 실행하세요.

---

## 실행 순서

### 1단계: dry-run 검증만

```powershell
python .\scripts\run_friday_from_notion.py
```

Notion에서 승인된 보고서를 가져와 발송 전 내용을 확인합니다.
실제 메일 발송은 하지 않습니다.

### 2단계: 실제 발송

```powershell
python .\scripts\run_friday_from_notion.py --execute-send
```

아래 순서로 자동 진행됩니다:
1. Notion에서 상태=승인 보고서 가져오기
2. 발송 전 dry-run 검증
3. 메일 발송
4. Notion 상태 → 발송완료 업데이트

---

## 개별 스크립트 직접 실행

```powershell
# Notion에서 승인된 보고서를 로컬로 복원만 할 때
python .\scripts\fetch_from_notion.py

# 복원된 로컬 파일로 발송만 할 때
python .\scripts\send_report.py --dry-run
python .\scripts\send_report.py
```

---

## 참고

- 승인된 Notion 페이지가 없으면 스크립트가 자동으로 중단됩니다.
- 메일 발송 성공 후 Notion 상태가 자동으로 "발송완료"로 변경됩니다.
- 발송시각도 Notion에 자동 기록됩니다.
