"""Local-only memory learner regressions. No models or real memories are touched."""
import contextlib
import importlib.machinery
import importlib.util
import io

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

LOADER = importlib.machinery.SourceFileLoader("memory_learn", str(Path(__file__).with_name("memory-learn")))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
learner = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(learner)
learner.BRAIN = tempfile.mkdtemp()  # keep tests away from the real ~/brain (no .git there, so no commit)


class MemoryEligibilityTests(unittest.TestCase):
    def test_denied_memory_skips_before_reading_transcripts_or_running_agent(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
            home = Path(directory)
            (home / "config.yaml").write_text("agent:\n  disabled_toolsets: [memory]\n")
            state = home / "state.json"
            output = io.StringIO()
            with patch.object(learner, "STATE", str(state)), \
                    patch.object(learner, "profiles", return_value=[("webchat", str(home))]), \
                    patch.object(learner, "messages", return_value=[]) as messages, \
                    patch.object(learner.subprocess, "run") as run, \
                    patch.object(learner.sys, "argv", ["memory-learn", "--verbose"]), \
                    contextlib.redirect_stdout(output):
                learner.main()
            messages.assert_not_called()
            run.assert_not_called()
            self.assertFalse(state.exists())
            self.assertIn("webchat: skipped", output.getvalue())

    def test_disabled_memory_stores_skip_without_reading_transcripts(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
            home = Path(directory)
            (home / "config.yaml").write_text(
                "memory:\n  memory_enabled: false\n  user_profile_enabled: false\n")
            with patch.object(learner, "STATE", str(home / "state.json")), \
                    patch.object(learner, "profiles", return_value=[("restricted", str(home))]), \
                    patch.object(learner, "messages", return_value=[]) as messages, \
                    patch.object(learner.subprocess, "run") as run, \
                    patch.object(learner.sys, "argv", ["memory-learn"]):
                learner.main()
            messages.assert_not_called()
            run.assert_not_called()

    def test_enabled_profile_is_still_selected_for_review(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
            home = Path(directory)
            (home / "config.yaml").write_text("{}\n")
            output = io.StringIO()
            rows = [(100, "discord", learner.OWNER_ID, "user", "Remember my preference.")]
            with patch.object(learner, "STATE", str(home / "state.json")), \
                    patch.object(learner, "profiles", return_value=[("default", str(home))]), \
                    patch.object(learner, "messages", return_value=rows) as messages, \
                    patch.object(learner.subprocess, "run") as run, \
                    patch.object(learner.sys, "argv", ["memory-learn", "--dry-run"]), \
                    contextlib.redirect_stdout(output):
                learner.main()
            messages.assert_called_once()
            run.assert_not_called()
            self.assertIn("default: 1 messages", output.getvalue())
            self.assertNotIn("skipped", output.getvalue())


if __name__ == "__main__":
    unittest.main()
