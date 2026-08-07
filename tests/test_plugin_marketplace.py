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
        self.assertEqual(manifest["version"], "0.3.0")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")

    def test_context_canvas_mcp_and_hook_commands_stay_inside_plugin(self):
        plugin_root = ROOT / "plugins" / "context-canvas-codex"
        mcp = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
        server = mcp["mcpServers"]["context-canvas"]
        self.assertEqual(server["command"], "python")
        self.assertEqual(server["args"], ["-B", "-I", "./scripts/context_canvas_mcp.py"])
        self.assertEqual(server["cwd"], ".")

        hooks = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(hooks["hooks"]), {"SessionStart", "PostToolUse"})
        groups = hooks["hooks"]["SessionStart"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["matcher"], "^(startup|resume|clear|compact)$")
        command = groups[0]["hooks"][0]["command"]
        self.assertIn("${PLUGIN_ROOT}/scripts/context_canvas.py", command)

        post_tool_groups = hooks["hooks"]["PostToolUse"]
        self.assertEqual(len(post_tool_groups), 1)
        self.assertEqual(post_tool_groups[0]["matcher"], ".*")
        post_tool_command = post_tool_groups[0]["hooks"][0]["command"]
        self.assertIn("${PLUGIN_ROOT}/scripts/context_canvas.py", post_tool_command)
        self.assertTrue(post_tool_command.endswith("hook-post-tool-use"))


if __name__ == "__main__":
    unittest.main()
