import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LongRunSupervisorContractTests(unittest.TestCase):
    def test_same_cell_continuation_is_awaited_long_and_exclusive(self):
        skill = (ROOT / "skills" / "long-run-supervisor" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(skill.split())
        for required in (
            "exact returned `cell_id`",
            "`120000` ms is the baseline for this runtime",
            "await functions.wait({",
            "Never fire-and-forget this continuation",
            "leave its promise unawaited",
            "background/parallel branch",
            "call `yield_control()`",
            "switch to `notify`",
            "the same cell",
            "another awaited",
            "long `functions.wait` for that same `cell_id`",
            "newly steered user message requires an immediate response",
            "let result = await tools.exec_command({",
            "cmd:",
            "result = await tools.write_stdin({",
        ):
            self.assertIn(required, normalized)
        self.assertNotIn("tools.shell_command", skill)

    def test_same_cell_transport_does_not_claim_post_turn_wake(self):
        skill = (ROOT / "skills" / "long-run-supervisor" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("This is synchronous continuation, not post-turn wake", skill)
        self.assertIn("It is not a fallback for a yielded execution", skill)
        self.assertIn("Do not switch that cell to `notify`", skill)
        self.assertNotIn("baton-dispatch", skill)


if __name__ == "__main__":
    unittest.main()
