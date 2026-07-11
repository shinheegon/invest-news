#!/usr/bin/env python3
"""Fail when an automated briefing run changes anything outside generated outputs."""
import subprocess
import sys

ALLOWED_PREFIXES = ("briefings/", "data/", "docs/data/", "logs/")

def lines(*args):
    out = subprocess.check_output(args, text=True)
    return [line.strip() for line in out.splitlines() if line.strip()]

def is_allowed(path):
    return any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES)

def main():
    changed = set(lines("git", "diff", "--name-only", "HEAD"))
    changed.update(lines("git", "ls-files", "--others", "--exclude-standard"))
    blocked = sorted(path for path in changed if not is_allowed(path))
    if blocked:
        print("::error::자동 브리핑이 보호 경로를 변경했습니다.")
        for path in blocked:
            print(f"  BLOCKED: {path}")
        return 1
    print(f"생성 산출물 경로 검사 통과 ({len(changed)} files)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
