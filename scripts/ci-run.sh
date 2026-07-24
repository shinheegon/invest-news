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
GUARD_COPY="$(mktemp)"
GUARD_STATE="$(mktemp)"
cleanup_guard() { rm -f "$GUARD_COPY" "$GUARD_STATE"; }
trap cleanup_guard EXIT

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
python3 "$PROJECT_DIR/scripts/build-krx-dict.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/niche-radar.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/macro-context.py" 2>&1 | tee -a "$LOG" || true

# --- 생성 에이전트가 코드·설정을 건드리지 못하도록 실행 전 기준점 저장 ---
cp "$PROJECT_DIR/scripts/agent-guard.py" "$GUARD_COPY"
if ! python3 "$GUARD_COPY" snapshot \
  --project "$PROJECT_DIR" --output "$GUARD_STATE" --date "$DATE" --session "$SESSION" \
  2>&1 | tee -a "$LOG"; then
  echo "[guard] 기준점 저장 실패" | tee -a "$LOG"
  exit 85
fi

# --- 브리핑 생성 (Claude Code 헤드리스, CLAUDE_CODE_OAUTH_TOKEN 사용) ---
claude -p "$(cat "$PROJECT_DIR/prompt/briefing-prompt.md")" \
  --permission-mode acceptEdits \
  --allowedTools "WebSearch,WebFetch,Read,Write,Edit" \
  2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}

# 에이전트가 스크립트·워크플로·프론트엔드 코드를 바꿨으면 즉시 차단한다.
if ! python3 "$GUARD_COPY" check \
  --project "$PROJECT_DIR" --output "$GUARD_STATE" --date "$DATE" --session "$SESSION" \
  2>&1 | tee -a "$LOG"; then
  echo "[$(TZ=Asia/Seoul date '+%F %T')] SECURITY BLOCK agent changed protected files" | tee -a "$LOG"
  exit 86
fi

if [ "$RC" -eq 0 ]; then
  echo "[$(TZ=Asia/Seoul date '+%F %T')] CLAUDE DONE session=$SESSION" | tee -a "$LOG"
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
python3 "$PROJECT_DIR/scripts/verify-patterns.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/cross-validate.py" 2>&1 | tee -a "$LOG" || true
python3 "$PROJECT_DIR/scripts/ai-group.py" 2>&1 | tee -a "$LOG" || true
bash "$PROJECT_DIR/scripts/build-site.sh" 2>&1 | tee -a "$LOG" || true

if [ "$RC" -eq 0 ]; then
  python3 "$PROJECT_DIR/scripts/validate-generated.py" \
    --project "$PROJECT_DIR" --date "$DATE" --session "$SESSION" \
    2>&1 | tee -a "$LOG"
  VALID_RC=${PIPESTATUS[0]}
  if [ "$VALID_RC" -ne 0 ]; then
    RC=87
  fi
fi

if [ "$RC" -eq 0 ]; then
  echo "$DATE-$SESSION" > "$MARKER"
  echo "[$(TZ=Asia/Seoul date '+%F %T')] CI VALIDATED session=$SESSION" | tee -a "$LOG"
  BRIEFING_SESSION="$SESSION" BRIEFING_DATE="$DATE" \
    python3 "$PROJECT_DIR/scripts/notify-email.py" 2>&1 | tee -a "$LOG" || true
else
  echo "[$(TZ=Asia/Seoul date '+%F %T')] EMAIL SKIP invalid or failed briefing" | tee -a "$LOG"
fi

# 생성·무결성·데이터 검증 중 하나라도 실패하면 워크플로를 실패 처리한다.
# 실패한 부분 산출물은 커밋·메일·배포하지 않는다.
exit "$RC"
