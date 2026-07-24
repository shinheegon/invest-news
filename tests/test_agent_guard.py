#!/usr/bin/env python3

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent-guard.py"


class AgentGuardTests(unittest.TestCase):
    def run_guard(self, command, project, state):
        return subprocess.run(
            [
                "python3",
                str(SCRIPT),
                command,
                "--project",
                str(project),
                "--output",
                str(state),
                "--date",
                "2026-07-24",
                "--session",
                "AM",
            ],
            capture_output=True,
            text=True,
        )

    def test_allows_generated_output_but_blocks_code_change(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "scripts").mkdir()
            (project / "data").mkdir()
            (project / "briefings").mkdir()
            (project / ".git" / "hooks").mkdir(parents=True)
            code = project / "scripts" / "worker.py"
            code.write_text("print('safe')\n", encoding="utf-8")
            state = project / "guard-state.json"

            self.assertEqual(self.run_guard("snapshot", project, state).returncode, 0)
            (project / "data" / "latest.md").write_text("generated", encoding="utf-8")
            self.assertEqual(self.run_guard("check", project, state).returncode, 0)

            code.write_text("print('changed')\n", encoding="utf-8")
            result = self.run_guard("check", project, state)
            self.assertEqual(result.returncode, 1)
            self.assertIn("scripts/worker.py", result.stdout)

    def test_blocks_new_git_hook(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".git" / "hooks").mkdir(parents=True)
            state = project / "guard-state.json"
            self.assertEqual(self.run_guard("snapshot", project, state).returncode, 0)

            (project / ".git" / "hooks" / "pre-commit").write_text(
                "#!/bin/sh\nexit 1\n", encoding="utf-8"
            )
            result = self.run_guard("check", project, state)

            self.assertEqual(result.returncode, 1)
            self.assertIn(".git/hooks/pre-commit", result.stdout)


if __name__ == "__main__":
    unittest.main()
