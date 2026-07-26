#!/usr/bin/env python3
"""Claude 실행 전후에 코드·설정 파일이 바뀌지 않았는지 검증한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


AGENT_OUTPUTS = {
    "data/analysis.md",
    "data/company-index.json",
    "data/discovery-index.json",
    "data/discovery-learnings.md",
    "data/discovery.md",
    "data/holdings-analysis.md",
    "data/keyword-index.json",
    "data/latest.md",
    "data/leading-index.json",
    "data/leading-signals.md",
    "data/market-indicators.json",
    "data/review.md",
    "data/synthesis-3day.md",
    "data/verification.json",
    "data/verification.md",
    "data/macro-analog.md",
    "data/macro-patterns.json",
    "data/value-scorecard.json",
}
RUNTIME_PATHS = {
    "data/news-feed.json",
    "data/news-feed.txt",
    "data/email-preview.html",
    "data/.run-lock",
}
SKIP_DIRS = {".git", "logs", "node_modules", "__pycache__"}


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(
    project: Path, date: str, session: str, output: Path | None = None
) -> dict[str, str]:
    allowed = set(AGENT_OUTPUTS)
    allowed.add(f"briefings/{date}-{session}.md")
    state: dict[str, str] = {}
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project).as_posix()
        if output is not None and path.resolve() == output.resolve():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(project).parts):
            continue
        if relative in allowed or relative in RUNTIME_PATHS or not path.is_file():
            continue
        state[relative] = file_digest(path)

    # Write/Edit 권한으로 Git 훅이나 로컬 설정을 심은 뒤 후속 commit/push 때
    # 실행시키는 경로도 막는다. .git 전체는 실행 중 변동이 커서 설정·훅만 보호한다.
    git_config = project / ".git" / "config"
    if git_config.is_file():
        state[".git/config"] = file_digest(git_config)
    hooks_dir = project / ".git" / "hooks"
    if hooks_dir.is_dir():
        for path in sorted(hooks_dir.rglob("*")):
            if path.is_file():
                relative = path.relative_to(project).as_posix()
                state[relative] = file_digest(path)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("snapshot", "check"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--session", required=True, choices=("AM", "PM"))
    args = parser.parse_args()

    project = Path(args.project).resolve()
    output = Path(args.output).resolve()
    current = snapshot(project, args.date, args.session, output)

    if args.command == "snapshot":
        output.write_text(
            json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[guard] 보호 파일 {len(current)}개 기준점 저장")
        return 0

    try:
        before = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"[guard] 기준점 읽기 실패: {error}")
        return 2

    added = sorted(set(current) - set(before))
    removed = sorted(set(before) - set(current))
    modified = sorted(
        path for path in set(before) & set(current) if before[path] != current[path]
    )
    if added or removed or modified:
        print("[guard] 차단: 생성 에이전트가 허용 범위 밖의 파일을 변경했습니다.")
        for label, paths in (("추가", added), ("삭제", removed), ("수정", modified)):
            for path in paths:
                print(f"  - {label}: {path}")
        return 1

    print("[guard] 코드·설정 무결성 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
