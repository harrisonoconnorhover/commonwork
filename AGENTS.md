# Commonwork

Commonwork coordinates volunteer AI-assisted work through GitHub issues and PRs.
This is a standalone project; never read or publish adjacent personal workspaces.

- Python 3.11+ standard library only. Run from the repository root with `python3 -m commonwork`.
- Run `python3 -m unittest discover -s tests -v` and `git diff --check` before delivery.
- The coordinator reads GitHub metadata; it must never execute task text, contributor code, or pull-request workflows with write credentials.
- GitHub workflows execute trusted default-branch code, never PR-head code. Keep permissions minimal and checkout credentials disabled.
- Votes are advisory, one per GitHub account and exact PR head commit. No automatic merging, token pooling, or hosted agent execution.
- Network writes require an explicit CLI command or configured workflow. Local demos and tests use fixtures only.
- Keep durable choices in `docs/decisions.md` and the final handoff under 500 words.
