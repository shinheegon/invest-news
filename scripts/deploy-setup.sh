#!/bin/bash
# GitHub Pages 공개 배포 1회 설정.
# 사용법:  bash scripts/deploy-setup.sh <github-원격-URL>
#   예:    bash scripts/deploy-setup.sh https://github.com/USERNAME/my-invest-news.git
set -euo pipefail
PROJECT_DIR="/Users/shinheekon/Desktop/ai-project/news"
cd "$PROJECT_DIR"

REMOTE="${1:-}"
if [ -z "$REMOTE" ]; then
  echo "❌ GitHub 원격 URL이 필요합니다."
  echo "   1) github.com 에서 빈 저장소(public) 생성 (예: my-invest-news)"
  echo "   2) bash scripts/deploy-setup.sh https://github.com/USERNAME/my-invest-news.git"
  exit 1
fi

# git 초기화
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init
  git branch -M main
fi

# 사이트 최신 빌드
bash scripts/build-site.sh

git add -A
git commit -m "init: 나만의 투자 브리핑 사이트" || echo "(커밋할 변경 없음)"

# 원격 등록(있으면 교체)
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"

echo ""
echo "▶ 푸시를 시도합니다 (GitHub 인증 창이 뜰 수 있습니다)…"
git push -u origin main

cat <<'EON'

✅ 푸시 완료!  이제 GitHub에서 Pages를 켜세요(1회):
   저장소 → Settings → Pages
   - Source: "Deploy from a branch"
   - Branch: main  /  폴더: /docs  → Save
   1~2분 뒤 공개 주소: https://USERNAME.github.io/저장소이름/

이후에는 매 브리핑(오전7시/오후7시)마다 자동으로 빌드·커밋·푸시되어
사이트가 갱신됩니다.
EON
