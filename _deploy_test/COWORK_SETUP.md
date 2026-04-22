# Design Center 주간보고 자동화 — Cowork 설정 가이드

## 1. 폴더 구조 세팅

Windows에서 아래 폴더를 만드세요:
```
C:\DesignCenter\
  ├── reports\        ← 초안/완료 보고서 저장
  ├── scripts\        ← Python 스크립트
  ├── config\         ← 설정 파일 (SMTP, Notion 키)
  └── archive\        ← 발송 완료본 이동
```

## 2. Cowork 프로젝트 생성

1. Claude Desktop 실행 → Cowork 탭 클릭
2. 좌측 상단 [+ New Project] 클릭
3. 프로젝트 이름: `Design Center 주간보고`
4. 폴더 연결: `C:\DesignCenter` 선택

## 3. Global Instructions 설정

Settings > Cowork > Edit Global Instructions에 아래 붙여넣기:

```
당신은 BMS Design Center의 주간업무보고 자동화 에이전트입니다.
- 보고서 초안 작성 시 항상 한국어로 작성합니다
- 파일은 반드시 C:\DesignCenter\reports\ 에 저장합니다
- 파일명 형식: report_W{주차}_{날짜}.md
- 발송 전 APPROVED 상태인 파일만 처리합니다
- 민감한 SMTP/API 정보는 config\secrets.json에서만 읽습니다
```

## 4. secrets.json 생성

`C:\DesignCenter\config\secrets.json` 파일 생성:

```json
{
  "smtp": {
    "host": "여기에_SMTP_주소",
    "port": 465,
    "user": "여기에_이메일주소",
    "password": "여기에_비밀번호"
  },
  "notion": {
    "api_key": "여기에_NOTION_API_KEY",
    "database_id": "여기에_DB_ID"
  },
  "recipients": [
    "사장님이메일@company.com",
    "부사장1@company.com",
    "부사장2@company.com",
    "이사1@company.com",
    "이사2@company.com",
    "팀장1@company.com"
  ],
  "sender_name": "Design Center"
}
```

