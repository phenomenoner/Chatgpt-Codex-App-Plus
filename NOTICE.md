# Notices and provenance

Original material authored for ChatGPT Codex App Plus is distributed under the repository MIT License.

`context-canvas-codex` is a clean Codex adaptation inspired by the factual-node to evidence-ref invariant in [phenomenoner/hermes-agent-harness-plus](https://github.com/phenomenoner/hermes-agent-harness-plus), compared at commit `7d6beb485d658a0342194c0e42edcdb7106ed1cb`. No upstream source code is copied. Both projects use the MIT License; the plugin carries its own `NOTICE` and `LICENSE`.

The following components are references only and are not redistributed or relicensed here:

- `baton-fanout-skill`: https://github.com/phenomenoner/baton-fanout-skill
- Understand Anything: https://github.com/Egonex-AI/Understand-Anything
- OpenAI skills: https://github.com/openai/skills

Exact pointer revisions are recorded in `manifest/public-sources.json` and `manifest/public-lock.json`. Consult each upstream repository for its current license, notices, installation instructions, and security policy.

The vendored collection contains integrations or workflows that refer to OpenAI Codex, ChatGPT, Claude, MCP, A2A, and other products or standards. Those names and trademarks belong to their respective owners. This independent community project is not endorsed by or affiliated with OpenAI, Anthropic, the Model Context Protocol project, or referenced upstream projects.

The public exporter records two narrowly scoped exceptions for an intentional protected-runtime deny marker in the Luna worker. These are safety checks, not machine paths or runtime contents; the exact files and reasons are visible in the source manifest. Secret findings cannot be exempted.
