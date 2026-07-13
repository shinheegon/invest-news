#!/bin/bash
# 클라우드(GitHub Actions)에서 브리핑 1회 실행. 맥과 무관하게 동작.
# 경로는 스크립트 위치 기준 상대경로. git/vercel 배포는 워크플로 YAML에서 처리.
set -uo pipefail
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1
LOG="$PROJECT_DIR/logs/run.log"
mkdir -p logs

# --- 한국시간 기준 날짜/회차 판정 ---
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
HOUR=$(TZ=Asia/Seoul date +%H)
if [ "${1:-}" = "AM" ] || [ "${1:-}" = "PM" ]; then
  SESSION="$1"
elif [ "$HOUR" -lt 12 ]; then SESSION="AM"; else SESSION="PM"; fi
export BRIEFING_SESSION="$SESSION" BRIEFING_DATE="$DATE"

# --- 멱등성 마커 ---
MARKER="$PROJECT_DIR/data/.last-session"
if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$DATE-$SESSION" ]; then
  export COUNT_MODE="skip"
else
  export COUNT_MODE="count"
fi
echo "[$(TZ=Asia/Seoul date '+%F %T')] CI START session=$SESSION date=$DATE count_mode=$COUNT_MODE" | tee -a "$LOG"

# --- 뉴스 RSS 전수 수집(브리핑 입력 코퍼스) ---
python3 "$PROJECT_DIR/scripts/collect-news.py" 2>&1 | tee -a "$LOG" || true

# --- 브리핑 생성 (Claude Code 헤드리스, CLAUDE_CODE_OAUTH_TOKEN 사용) ---
claude -p "$(cat "$PROJECT_DIR/prompt/briefing-prompt.md")" \
  --permission-mode acceptEdits \
  --allowedTools "WebSearch,WebFetch,Read,Write,Edit,Bash" \
  2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}

if [ "$RC" -eq 0 ]; then
  echo "$DATE-$SESSION" > "$MARKER"
  echo "[$(TZ=Asia/Seoul date '+%F %T')] CI DONE session=$SESSION" | tee -a "$LOG"
else
  echo "[$(TZ=Asia/Seoul date '+%F %T')] CI ERROR rc=$RC" | tee -a "$LOG"
fi

# --- 투자지표 히스토리 + 검증 통계 + 사이트 빌드 + 이메일 발송 ---
BRIEFING_DATE="$DATE" python3 "$PROJECT_DIR/scripts/track-indicators.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/score-predictions.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/verify-stats.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/price-history.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/theme-scoreboard.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/watch-priority.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/miss-analysis.py" 2>&1 | tee -a "$LOG" || true
bash "$PROJECT_DIR/scripts/build-site.sh" 2>&1 | tee -a "$LOG" || true
BRIEFING_SESSION="$SESSION" BRIEFING_DATE="$DATE" \
  python3 "$PROJECT_DIR/scripts/notify-email.py" 2>&1 | tee -a "$LOG" || true

# claude가 실패했으면(RC≠0) 워크플로가 빨간불로 뜨도록 그 코드로 종료.
# (부분 산출물은 위에서 이미 생성됨 — 커밋 단계는 워크플로에서 if:always()로 진행)
exit "$RC"
