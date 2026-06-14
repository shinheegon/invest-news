#!/bin/bash
# 로컬에서 사이트 미리보기. 브라우저에서 http://localhost:8765 접속.
# (file:// 로 직접 열면 데이터 fetch가 막히므로 반드시 이 서버로 확인)
set -euo pipefail
cd "/Users/shinheekon/Desktop/ai-project/news/docs"
PORT="${1:-8765}"
echo "▶ http://localhost:$PORT  (종료: Ctrl+C)"
python3 -m http.server "$PORT"
