import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATON_URL = "https://github.com/phenomenoner/baton-fanout-skill"
BATON_COMMIT = "ed12ef2330309b93963f9a61bc5ee7de53cf0956"


class NativeSubagentRoutingTests(unittest.TestCase):
    def test_baton_pointer_targets_unified_main(self):
        manifest = json.loads(
            (ROOT / "manifest" / "public-sources.json").read_text(encoding="utf-8")
        )
        components = {item["id"]: item for item in manifest["components"]}
        baton = components["baton-fanout-skill"]
        self.assertEqual(baton["canonicalUrl"], BATON_URL)
        self.assertEqual(baton["version"], "1.1.0")
        self.assertEqual(baton["commit"], BATON_COMMIT)

        catalog = json.loads(
            (ROOT / "catalog" / "components.json").read_text(encoding="utf-8")
        )
        entries = {item["id"]: item for item in catalog["components"]}
        self.assertEqual(entries["baton-fanout-skill"]["canonicalUrl"], BATON_URL)

    def test_public_guidance_uses_native_subagents(self):
        config = (ROOT / "config" / "config.example.toml").read_text(encoding="utf-8")
        agents = (ROOT / "config" / "AGENTS.example.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_en = (ROOT / "README.en.md").read_text(encoding="utf-8")
        page = (ROOT / "pages" / "index.html").read_text(encoding="utf-8")

        for required in (
            "default_subagent_model",
            "default_subagent_reasoning_effort",
        ):
            self.assertIn(required, config)
            self.assertIn(required, readme)

        self.assertIn('model: "gpt-5.6-luna"', agents)
        self.assertIn('reasoning_effort: "max"', agents)
        self.assertIn("explicit per-spawn", readme_en)
        self.assertIn("NATIVE SPAWN", page)
        self.assertIn("native subagent", page)

        active_surfaces = "\n".join((config, agents, readme, readme_en, page))
        self.assertNotIn("codex-cli-luna-worker", active_surfaces)
        self.assertNotIn("LUNA BRIDGE", active_surfaces)
        self.assertNotIn("tree/codex/add-model-effort-routing", active_surfaces)


if __name__ == "__main__":
    unittest.main()
