#!/bin/bash
# 매일 2회 투자 브리핑 실행 래퍼 (launchd가 호출)
# 복원력: ①중복실행 잠금+잔여정리 ②타임아웃 ③실패 시 자동 재시도 ④성공시에만 집계확정
set -uo pipefail

# --- 경로 설정 ---
PROJECT_DIR="/Users/shinheekon/Desktop/ai-project/news"
export PATH="/Users/shinheekon/.local/bin:/Users/shinheekon/.local/node/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# 로컬 비밀키(이메일 등) — 맥에만 보관, git에 안 올라감
[ -f "$HOME/.news-briefing.env" ] && set -a && . "$HOME/.news-briefing.env" && set +a
cd "$PROJECT_DIR" || exit 1

LOG="$PROJECT_DIR/logs/run.log"
mkdir -p "$PROJECT_DIR/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 튜닝 값(환경변수로 덮어쓰기 가능)
ATTEMPT_TIMEOUT="${ATTEMPT_TIMEOUT:-2700}"   # 1회 시도 최대 45분(검증·다단계로 작업량 증가 대응)
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"            # 실패 시 최대 3회 시도
RETRY_WAIT="${RETRY_WAIT:-45}"               # 재시도 간 대기(초)

# --- ① 중복 실행 잠금 + 잔여(좀비) 프로세스 정리 ---
LOCK="$PROJECT_DIR/data/.run-lock"
if [ -f "$LOCK" ]; then
  OLDPID="$(cat "$LOCK" 2>/dev/null)"
  if [ -n "${OLDPID:-}" ] && kill -0 "$OLDPID" 2>/dev/null; then
    echo "[$(ts)] SKIP 이미 실행 중(pid $OLDPID) — 중복 방지 종료" >> "$LOG"
    exit 0
  fi
  echo "[$(ts)] CLEAN 죽은 잠금 정리(pid ${OLDPID:-?})" >> "$LOG"
  rm -f "$LOCK"
  # 이전 회차가 남긴 좀비 헤드리스 프로세스가 있으면 정리(이 프롬프트 전용으로 한정)
  pkill -f "claude -p # 투자용 경제뉴스 브리핑 생성 지시문" 2>/dev/null && \
    echo "[$(ts)] CLEAN 잔여 claude 프로세스 종료" >> "$LOG"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# --- ⭐ 잠들기 방지: 브리핑이 도는 내내 맥을 깨어있게 잡아둔다 ---
# (실행 중 맥이 자면 claude도 타임아웃 타이머도 같이 얼어 무한 hang → 이게 핵심 원인이었음)
# caffeinate -w $$ : 이 스크립트(pid $$)가 끝날 때까지만 유지하고 자동 종료.
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -i -m -s -w $$ &
  echo "[$(ts)] CAFFEINATE on (실행 중 절전 방지)" >> "$LOG"
fi

# --- ② 타임아웃 실행 헬퍼(맥 기본 환경엔 timeout 명령이 없어 직접 구현) ---
run_with_timeout() {
  local secs="$1"; shift
  "$@" &
  local pid=$!
  ( sleep "$secs"
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null
      sleep 8
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
    fi ) &
  local killer=$!
  wait "$pid" 2>/dev/null
  local rc=$?
  kill "$killer" 2>/dev/null
  wait "$killer" 2>/dev/null
  return "$rc"
}

# --- 네트워크 복구 대기: 절전에서 깨어난 직후엔 WiFi가 아직 안 붙어 ConnectionRefused가 난다.
#     인터넷이 붙을 때까지 최대 ~3분 기다린다(붙으면 즉시 진행). ---
wait_for_network() {
  local tries="${1:-18}"   # 18 x 10s = 최대 180초
  local i=0
  while [ "$i" -lt "$tries" ]; do
    if curl -s -o /dev/null --max-time 6 https://api.anthropic.com/ping 2>/dev/null \
       || curl -s -o /dev/null --max-time 6 https://www.google.com 2>/dev/null; then
      [ "$i" -gt 0 ] && echo "[$(ts)] NET ready (${i}회 대기 후)" >> "$LOG"
      return 0
    fi
    i=$((i + 1)); sleep 10
  done
  echo "[$(ts)] WARN 네트워크 미복구(${tries}회 대기 초과) — 그래도 시도" >> "$LOG"
  return 1
}

# --- 회차(AM/PM) 판정: 인자 > 환경변수 > 현재시각 ---
SESSION="${1:-${BRIEFING_SESSION:-}}"
if [ -z "$SESSION" ]; then
  HOUR=$(date +%H)
  if [ "$HOUR" -lt 12 ]; then SESSION="AM"; else SESSION="PM"; fi
fi
DATE=$(date +%Y-%m-%d)
export BRIEFING_SESSION="$SESSION"
export BRIEFING_DATE="$DATE"

# --- 멱등성: 같은 날짜+회차가 이미 집계됐으면 카운트 중복 방지 ---
MARKER="$PROJECT_DIR/data/.last-session"
if [ -f "$MARKER" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$DATE-$SESSION" ]; then
  export COUNT_MODE="skip"   # 이미 집계됨 → 인덱스 증가 금지, 콘텐츠만 재생성
else
  export COUNT_MODE="count"  # 신규 회차 → 정상 집계
fi

PROMPT="$(cat "$PROJECT_DIR/prompt/briefing-prompt.md")"
echo "[$(ts)] START session=$SESSION date=$DATE count_mode=$COUNT_MODE" >> "$LOG"

# 절전 복귀 직후일 수 있으니 네트워크부터 기다린다
wait_for_network 18

# --- 뉴스 RSS 전수 수집(브리핑 입력 코퍼스) — 누락 최소화 ---
python3 "$PROJECT_DIR/scripts/collect-news.py" >> "$LOG" 2>&1 \
  && echo "[$(ts)] NEWS collected" >> "$LOG" \
  || echo "[$(ts)] WARN news collect failed (브리핑은 계속)" >> "$LOG"

# --- ③ 타임아웃+재시도 루프로 헤드리스 Claude 실행 ---
RC=1
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  echo "[$(ts)] ATTEMPT $attempt/$MAX_ATTEMPTS (timeout ${ATTEMPT_TIMEOUT}s)" >> "$LOG"
  run_with_timeout "$ATTEMPT_TIMEOUT" \
    claude -p "$PROMPT" \
      --permission-mode acceptEdits \
      --allowedTools "WebSearch,WebFetch,Read,Write,Edit,Bash" \
    >> "$LOG" 2>&1
  RC=$?
  if [ "$RC" -eq 0 ]; then
    break
  fi
  echo "[$(ts)] ATTEMPT $attempt 실패 rc=$RC" >> "$LOG"
  # 첫 집계 시도가 일부라도 증분했을 수 있으니, 재시도는 중복 방지를 위해 skip 모드로
  export COUNT_MODE="skip"
  if [ "$attempt" -lt "$MAX_ATTEMPTS" ]; then
    sleep "$RETRY_WAIT"
    wait_for_network 18   # 재시도 전에도 네트워크 확인(깨어난 직후 대비)
  fi
done

if [ "$RC" -eq 0 ]; then
  echo "$DATE-$SESSION" > "$MARKER"   # ④ 성공했을 때만 집계 완료 확정
  echo "[$(ts)] DONE  session=$SESSION rc=0" >> "$LOG"
else
  echo "[$(ts)] ERROR session=$SESSION rc=$RC ($MAX_ATTEMPTS회 모두 실패)" >> "$LOG"
fi

# --- 투자지표 히스토리 누적(추세 그래프 원천) ---
BRIEFING_DATE="$DATE" python3 "$PROJECT_DIR/scripts/track-indicators.py" >> "$LOG" 2>&1 || \
  echo "[$(ts)] WARN track-indicators failed" >> "$LOG"

# --- 예측 자동 채점(네이버 금융, 초과수익률 기준) → 통계 재계산 ---
python3 "$PROJECT_DIR/scripts/score-predictions.py" >> "$LOG" 2>&1 || \
  echo "[$(ts)] WARN score-predictions failed" >> "$LOG"
python3 "$PROJECT_DIR/scripts/verify-stats.py" >> "$LOG" 2>&1 || \
  echo "[$(ts)] WARN verify-stats failed" >> "$LOG"

# --- 발굴/선행 종목 주가 곡선 생성(최초 등장~현재) ---
python3 "$PROJECT_DIR/scripts/price-history.py" >> "$LOG" 2>&1 || \
  echo "[$(ts)] WARN price-history failed" >> "$LOG"

# --- 테마 스코어보드(검증기반 자기학습 피드백) ---
python3 "$PROJECT_DIR/scripts/theme-scoreboard.py" >> "$LOG" 2>&1 || \
  echo "[$(ts)] WARN theme-scoreboard failed" >> "$LOG"

# --- 유망 대기 선별(학습패턴 기반, 네트워크 없음) ---
python3 "$PROJECT_DIR/scripts/watch-priority.py" >> "$LOG" 2>&1 || \
  echo "[$(ts)] WARN watch-priority failed" >> "$LOG"

# --- 사이트 빌드 + GitHub 배포 (git 원격이 설정된 경우에만 push) ---
bash "$PROJECT_DIR/scripts/build-site.sh" >> "$LOG" 2>&1 || \
  echo "[$(ts)] WARN build-site failed" >> "$LOG"

if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$PROJECT_DIR" add -A >> "$LOG" 2>&1 || true
  if ! git -C "$PROJECT_DIR" diff --cached --quiet 2>/dev/null; then
    git -C "$PROJECT_DIR" commit -m "briefing: $DATE $SESSION" >> "$LOG" 2>&1 || true
    if git -C "$PROJECT_DIR" remote get-url origin >/dev/null 2>&1; then
      git -C "$PROJECT_DIR" push origin HEAD >> "$LOG" 2>&1 \
        && echo "[$(ts)] PUSHED $DATE $SESSION" >> "$LOG" \
        || echo "[$(ts)] WARN push failed (인증/원격 확인)" >> "$LOG"
    fi
  fi
fi

# --- 이메일 요약 + 급등 알림 발송 (RESEND_API_KEY 있으면 발송) ---
BRIEFING_SESSION="$SESSION" BRIEFING_DATE="$DATE" \
  python3 "$PROJECT_DIR/scripts/notify-email.py" >> "$LOG" 2>&1 \
  && echo "[$(ts)] EMAIL sent/preview $DATE $SESSION" >> "$LOG" \
  || echo "[$(ts)] WARN email failed" >> "$LOG"

# --- Vercel 자동 재배포 (docs/.vercel 링크가 있으면 = 최초 배포 완료 후) ---
if command -v vercel >/dev/null 2>&1 && [ -f "$PROJECT_DIR/docs/.vercel/project.json" ]; then
  ( cd "$PROJECT_DIR/docs" && vercel deploy --prod --yes >> "$LOG" 2>&1 ) \
    && echo "[$(ts)] VERCEL DEPLOYED $DATE $SESSION" >> "$LOG" \
    || echo "[$(ts)] WARN vercel deploy failed (vercel login 확인)" >> "$LOG"
fi
exit $RC
