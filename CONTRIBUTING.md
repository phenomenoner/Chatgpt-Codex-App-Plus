# Contributing

Contributions are welcome when they keep the bundle focused, public-safe, and easy to audit.

Before opening a pull request:

1. Explain the reusable user outcome and why a direct link is insufficient.
2. Preserve upstream attribution and prefer a pointer when a canonical public source exists.
3. Add source files only through the explicit manifest; never mirror a personal tool directory.
4. Run `python -m unittest discover -s tests -v` and `python scripts/public_sync.py validate`.
5. Read the complete public diff for private paths, identities, credentials, internal shorthand, stale claims, and licensing changes.

Scanner or manifest authority changes require focused tests that first demonstrate the unsafe or incomplete behavior. A passing scanner is necessary but does not replace human review of public prose and provenance.

Keep commits small and describe behavior rather than private milestone names. By contributing, you agree that your original contribution may be distributed under this repository's MIT License.
