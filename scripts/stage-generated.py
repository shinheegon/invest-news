#!/usr/bin/env python3
"""자동 실행이 만든 허용된 산출물만 git stage에 올린다."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


GENERATED_DATA = (
    ".last-session",
    "ai-group-live.json",
    "ai-group.json",
    "analysis.md",
    "article-archive.json",
    "company-index.json",
    "discovery-index.json",
    "discovery-learnings.md",
    "discovery.md",
    "holdings-analysis.md",
    "keyword-index.json",
    "latest.md",
    "leading-index.json",
    "leading-signals.md",
    "market-history.json",
    "market-indicators.json",
    "miss-analysis.json",
    "price-history.json",
    "review.md",
    "synthesis-3day.md",
    "theme-scoreboard.json",
    "verification.json",
    "verification.md",
    "watch-priority.json",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=".")
    parser.add_argument("--date", required=True)
    parser.add_argument("--session", required=True, choices=("AM", "PM"))
    args = parser.parse_args()

    project = Path(args.project).resolve()
    paths = []
    for filename in GENERATED_DATA:
        root_path = project / "data" / filename
        if root_path.exists():
            paths.append(root_path.relative_to(project).as_posix())
        docs_path = project / "docs" / "data" / filename
        if docs_path.exists():
            paths.append(docs_path.relative_to(project).as_posix())

    for relative in (
        f"briefings/{args.date}-{args.session}.md",
        f"docs/data/briefings/{args.date}-{args.session}.md",
        "docs/data/briefings.json",
    ):
        if (project / relative).exists():
            paths.append(relative)

    if not paths:
        print("[stage] 허용된 생성 산출물 없음")
        return 0
    subprocess.run(["git", "add", "--", *paths], cwd=project, check=True)
    print(f"[stage] 허용된 생성 산출물 {len(paths)}개만 stage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

