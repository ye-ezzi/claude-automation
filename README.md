# Claude Automation — 릴스 자동화 도구 모음

인스타그램 콘텐츠 자동화를 위한 세 가지 독립 도구입니다.

---

## 도구 구성

| 파일 | 목적 | 실행 시간 |
|------|------|-----------|
| `AI_reels_planner.py` | AI/디자인 계정 릴스 아이디어 20개 생성 → Gmail 발송 | 매일 오전 9시 |
| `finance_reels_planner.py` | 재테크 계정 릴스 아이디어 20개 생성 → Gmail 발송 | 매일 오전 9시 |
| `reels_translator.py` | 벤치마킹 계정 릴스 음성 번역 → Gmail 발송 | 매일 오후 9시 |

---

## 1. AI_reels_planner.py — AI/콘텐츠 릴스 플래너

**타겟 계정:** AI 툴 & 크리에이티브 도구 계정 (20-30대 디자이너/크리에이터/프리랜서)

**동작 방식:**
1. Google Sheets (Apps Script)에서 기존 AI/디자인 콘텐츠 패턴 수집
2. DuckDuckGo로 오늘의 AI툴·디자인·크리에이터 이코노미 트렌드 검색
3. Claude API (`claude-opus-4-6`)로 릴스 아이디어 20개 생성
4. Gmail로 HTML 이메일 발송 (실패 시 `~/reels_outputs/reels-ai-{날짜}.md` 저장)

**러너 스크립트:** `run_reels_planner.sh`

---

## 2. finance_reels_planner.py — 재테크 릴스 플래너

**타겟 계정:** 재테크/경제 계정 (20-30대 직장인/사회초년생)

**동작 방식:**
1. Google Sheets (Apps Script)에서 기존 재테크/경제/투자 콘텐츠 패턴 수집
2. DuckDuckGo로 오늘의 주식·ETF·부동산·절세 트렌드 검색
3. Claude API (`claude-opus-4-6`)로 릴스 아이디어 20개 생성
4. Gmail로 HTML 이메일 발송 (실패 시 `~/reels_outputs/reels-finance-{날짜}.md` 저장)

**러너 스크립트:** 별도 `run_finance_planner.sh` 필요 (아래 참고)

---

## 3. reels_translator.py — 릴스 번역 모니터

**목적:** 벤치마킹 대상 인스타그램 계정의 릴스를 자동 수집·번역

**동작 방식:**
1. Chrome 쿠키로 Instagram API 인증
2. 대상 계정 릴스 메타데이터 수집 (조회수, 업로드일, 썸네일)
3. Whisper로 음성 인식 → 한국어 번역
4. Gmail로 HTML 리포트 발송

**러너 스크립트:** `run_reels_monitor.sh`

---

## 설치 및 실행

### 패키지 설치

```bash
pip install anthropic requests duckduckgo-search
pip install yt-dlp openai-whisper deep-translator browser-cookie3  # reels_translator용
```

### API 키 설정

```bash
# .env 파일 생성 (run_reels_planner.sh가 자동으로 로드)
echo "ANTHROPIC_API_KEY=sk-ant-..." > /path/to/claude-automation/.env
```

### 크론 등록

```bash
bash setup_cron.sh
```

등록 후 확인:
```
0 9  * * * /path/to/run_reels_planner.sh    # AI 릴스 플래너 (오전 9시)
0 21 * * * /path/to/run_reels_monitor.sh    # 릴스 번역 모니터 (오후 9시)
```

### 수동 실행

```bash
# AI 릴스 플래너
ANTHROPIC_API_KEY=sk-ant-... python3 AI_reels_planner.py

# 재테크 릴스 플래너
ANTHROPIC_API_KEY=sk-ant-... python3 finance_reels_planner.py

# 릴스 번역 모니터
python3 reels_translator.py --monitor
```

---

## 로그 확인

```bash
# AI 릴스 플래너 로그
ls ~/logs/reels_planner_*.log

# 릴스 번역 모니터 로그
ls ~/logs/reels_monitor_*.log
```
