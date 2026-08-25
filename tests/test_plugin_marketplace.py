import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginMarketplaceContractTests(unittest.TestCase):
    def test_context_canvas_marketplace_entry_resolves_to_checked_in_plugin(self):
        marketplace_path = ROOT / ".agents" / "plugins" / "marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))

        self.assertEqual(marketplace["name"], "codex-app-plus")
        entries = {entry["name"]: entry for entry in marketplace["plugins"]}
        entry = entries["context-canvas-codex"]
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")

        source = entry["source"]
        self.assertEqual(source["source"], "local")
        marketplace_root = marketplace_path.parents[2]
        plugin_root = (marketplace_root / source["path"]).resolve()
        self.assertTrue(plugin_root.is_relative_to(ROOT.resolve()))
        self.assertTrue(plugin_root.is_dir())

        manifest = json.loads(
            (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["name"], "context-canvas-codex")
        base_version, separator, build_metadata = manifest["version"].partition("+")
        self.assertEqual(base_version, "0.7.0")
        self.assertEqual(separator, "+")
        self.assertRegex(
            build_metadata,
            r"^codex\.[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*$",
        )
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertLessEqual(len(manifest["interface"]["defaultPrompt"]), 3)

    def test_context_canvas_reflection_skill_stays_bounded_and_advisory(self):
        skill_root = (
            ROOT
            / "plugins"
            / "context-canvas-codex"
            / "skills"
            / "context-canvas-reflection"
        )
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        openai_yaml = (skill_root / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("name: context-canvas-reflection", skill_text)
        self.assertIn("CONTINUE | INVESTIGATE | ESCALATE", skill_text)
        self.assertIn("at most one bounded", skill_text)
        self.assertIn("at most one `reference_search`", skill_text)
        self.assertIn("at most two bounded", skill_text)
        self.assertIn("Do not\n   call `canvas_search`", skill_text)
        self.assertIn("`snapshot_read`", skill_text)
        self.assertIn("one reflection per active trigger and evidence watermark", skill_text)
        self.assertIn("continue a Canvas solely for this skill", skill_text)
        self.assertIn("advisory", skill_text.lower())
        self.assertIn("The owner's response is not a fresh watermark", skill_text)
        self.assertIn("at most three implicit reflection", skill_text)
        self.assertIn("next_safe_action: present_to_owner", skill_text)
        self.assertIn("[reflection-proposal]", skill_text)
        self.assertIn("Current conversation, current owner decisions", skill_text)
        self.assertIn("Do not automatically pause a harness", skill_text)
        self.assertIn("must not recursively trigger", skill_text)
        self.assertIn("$context-canvas-reflection", openai_yaml)
        self.assertIn("allow_implicit_invocation: false", openai_yaml)

    def test_context_canvas_mcp_and_hook_commands_stay_inside_plugin(self):
        plugin_root = ROOT / "plugins" / "context-canvas-codex"
        mcp = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp["mcpServers"]["context-canvas"]
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"], ["-B", "-I", "./scripts/context_canvas_mcp.py"])
        self.assertEqual(server["cwd"], ".")

        hooks = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(
            set(hooks["hooks"]),
            {"SessionStart", "UserPromptSubmit", "PostToolUse"},
        )
        groups = hooks["hooks"]["SessionStart"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["matcher"], "^(startup|resume|clear|compact)$")
        command = groups[0]["hooks"][0]["command"]
        self.assertIn("${PLUGIN_ROOT}/scripts/context_canvas.py", command)

        prompt_groups = hooks["hooks"]["UserPromptSubmit"]
        self.assertEqual(len(prompt_groups), 1)
        self.assertNotIn("matcher", prompt_groups[0])
        prompt_command = prompt_groups[0]["hooks"][0]["command"]
        self.assertTrue(prompt_command.endswith("hook-user-prompt-submit"))

        post_tool_groups = hooks["hooks"]["PostToolUse"]
        self.assertEqual(len(post_tool_groups), 1)
        self.assertEqual(post_tool_groups[0]["matcher"], ".*")
        post_tool_command = post_tool_groups[0]["hooks"][0]["command"]
        self.assertIn("${PLUGIN_ROOT}/scripts/context_canvas.py", post_tool_command)
        self.assertTrue(post_tool_command.endswith("hook-post-tool-use"))


if __name__ == "__main__":
    unittest.main()
