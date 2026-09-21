# 인디알리미 (indie-alimi)

지원사업 게시판 → Discord 알림 봇

등록된 사이트들(기본: 콘진원)을 키워드(기본: `게임`, `인디`)로 모니터링해서,
새 공고가 올라오면 Discord 채널에 알려줍니다. 슬래시 커맨드로 소스 추가/조회도 가능합니다.

두 가지 실행 방식이 있습니다:

| 파일 | 방식 | 필요한 것 | 슬래시 커맨드 |
|---|---|---|---|
| `scraper.py` | 스크립트를 주기적으로 실행 → 새 글이면 Webhook 전송 | Webhook URL | ❌ |
| `bot.py` | **상시 실행되는 봇** (주기 알림 + 슬래시 커맨드 둘 다) | Bot Token + Webhook URL | ✅ |

`/add-source`, `/all-source`, `/all-alim` 같은 슬래시 커맨드를 쓰려면 **`bot.py`를 상시 실행**해야 합니다.
(디스코드가 명령어를 받으려면 봇이 항상 접속해 있어야 해서, Webhook만으로는 안 됩니다.)

## 1. Discord Webhook 만들기 (알림용)

1. 알림 받을 채널 → 채널 설정 → 연동 → 웹후크 → 새 웹후크
2. "웹후크 URL 복사" → `.env`의 `DISCORD_WEBHOOK_URL`에 붙여넣기

## 2. Discord Bot 만들기 (슬래시 커맨드용)

1. https://discord.com/developers/applications → **New Application** → 이름 "인디알리미"
2. 좌측 **Bot** 탭 → **Reset Token**으로 토큰 발급 → 복사 → `.env`의 `DISCORD_BOT_TOKEN`에 붙여넣기
   (토큰은 비밀번호처럼 다뤄야 해요. 절대 공개 채널/코드에 올리지 마세요.)
3. 좌측 **OAuth2 → URL Generator**
   - SCOPES: `bot`, `applications.commands` 체크
   - BOT PERMISSIONS: `Send Messages`, `Embed Links` 체크
   - 생성된 URL을 브라우저에 열어서 내 서버에 봇 초대

## 3. 설치 & 실행

```bash
pip install -r requirements.txt
copy .env.example .env
```

`.env`를 열어 `DISCORD_WEBHOOK_URL`, `DISCORD_BOT_TOKEN`을 채워넣으세요.

```bash
python bot.py
```

콘솔에 `인디알리미 로그인 완료: ...`가 뜨면 성공. 디스코드 서버에서 `/add-source`, `/all-source`,
`/all-alim`이 바로 보입니다 (안 보이면 디스코드 클라이언트 재시작).

봇을 계속 켜두지 않고 알림만 받고 싶다면 `bot.py` 대신 `python scraper.py`를 주기적으로 실행해도
됩니다 (이 경우 슬래시 커맨드는 동작하지 않음).

## 4. 슬래시 커맨드

- `/add-source link:<URL>` — 새 게시판/목록 페이지를 모니터링 대상으로 추가.
  콘진원처럼 구조를 정확히 아는 사이트가 아니면 **일반 파서(generic)**로 동작합니다:
  페이지의 링크 텍스트 중 키워드가 포함된 것만 공고로 인식합니다. 목록이 아니라
  JS로 렌더링되는 페이지(예: React SPA)는 감지가 안 될 수 있어요.
- `/all-source` — 지금 등록된 소스(사이트) 전체 목록.
- `/all-alim` — 지금 이 순간 각 소스를 다시 긁어서, 키워드에 걸리는 공고를 전부 출력.
  (라이브 조회라 사이트 개수/속도에 따라 몇 초 걸릴 수 있습니다.)

소스는 `sources.json`, 이미 알린 공고 id는 `seen_ids.json`에 저장됩니다.

## 5. 키워드 바꾸기

`.env`의 `KEYWORDS`에 쉼표로 구분해서 넣으면 됩니다.

```
KEYWORDS=게임,인디,인디게임
```

## 6. 계속 켜두는 방법

`bot.py`는 상시 접속이 필요해서, `scraper.py`처럼 GitHub Actions 크론으로는 못 돌립니다
(크론은 짧게 실행되고 끝나는 방식이라 슬래시 커맨드를 받을 수 없음). 옵션:

- **내 PC**: 그냥 터미널 하나 켜놓고 `python bot.py` 실행 (재부팅 시 다시 실행해야 함)
- **무료/저가 상시 호스팅**: Railway, Fly.io, Replit 등 (24시간 켜둘 수 있는 곳) — 완전 무료 티어는
  제한이 있는 경우가 많아 사용량 보고 선택하면 좋아요
- 알림만 필요하고 슬래시 커맨드는 필요 없다면, `scraper.py` + GitHub Actions(무료) 조합이 제일 간단합니다
  (`.github/workflows/scrape.yml` 참고)

## 확장 아이디어

- 마감일 임박 알림: `접수기간`의 종료일을 파싱해서 D-3일 때 리마인드
- `/remove-source` 커맨드 추가
- 사이트별 전용 파서 추가 (예술경영지원센터, 인디크래프트 등) — `scraping.py`의 `PARSERS`에 등록
