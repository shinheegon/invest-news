#!/usr/bin/env python3

import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "stage-generated.py"


class StageGeneratedTests(unittest.TestCase):
    def test_stages_only_allowlisted_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "data").mkdir()
            (project / "scripts").mkdir()
            (project / "data" / "latest.md").write_text(
                "generated", encoding="utf-8"
            )
            (project / "scripts" / "unexpected.py").write_text(
                "print('must not stage')\n", encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q"], cwd=project, check=True)

            subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--project",
                    str(project),
                    "--date",
                    "2026-07-24",
                    "--session",
                    "AM",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=project,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()

        self.assertEqual(staged, ["data/latest.md"])


if __name__ == "__main__":
    unittest.main()
