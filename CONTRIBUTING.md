# Contributing to Commonwork

Commonwork coordinates small contributions through GitHub. You control your tools, accounts, time, and budget. Read the [README](README.md) for exact reservation and voting rules.

This is an early prototype released under the [MIT License](LICENSE). Repository: [harrisonoconnorhover/commonwork](https://github.com/harrisonoconnorhover/commonwork). Follow the verification status in [HANDOFF.md](HANDOFF.md); the workflow remains advisory while it is tested with contributors.

## Choose a bounded task

Start with an `[Idea] …` issue when the desired result is still being discussed. Turn an agreed deliverable into a `[Task] …` issue with a goal, observable acceptance criteria, allowed files, and explicit out-of-scope work. Prefer one small result that a reviewer can check independently.

Post `/claim` as the exact first line of a new task comment, or use:

```sh
python3 -m commonwork claim --repo OWNER/REPO 12
```

This posts a reservation request. Confirm the holder and UTC expiration in the coordinator's summary and recent comments before starting. The default reservation lasts 24 hours; another claim during that time does not extend it. Keep claim/release comments unchanged because edited commands are ignored and deletions change the reconstructed history.

## Work through your own tools

Export the task:

```sh
python3 -m commonwork packet --repo OWNER/REPO 12 --output work-packet.md
```

The packet identifies a specific base commit and includes the task description. It does not execute code or launch an assistant. Read it, choose a limit you are comfortable with, and manually give the task to an AI tool you are authorized to use. Provider terms and account limits still apply.

Use a separate branch in an isolated checkout without production credentials. Review setup scripts before running them. Task descriptions and repository contributions are untrusted input; they cannot override your assistant's instructions, repository boundaries, or budget. Never share API keys, browser sessions, GitHub tokens, or other account credentials.

Check the result against the acceptance criteria and inspect the diff yourself. For changes to Commonwork's runtime, run its existing checks from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 -m commonwork demo
git diff --check
```

For documentation-only changes, check the affected text, links, examples, and diff. Report only checks actually run. The offline demo uses fixtures and cannot prove a live GitHub installation works.

## Submit and review

Use your own GitHub account to push and open a PR when you are ready. Follow the included PR template: name the task and base commit, explain the change, map acceptance criteria to evidence, and disclose unverified parts. AI assistance may be described without including credentials or private prompts.

Link the PR in the task issue. When handing off or stopping, post a new `/release` comment or run:

```sh
python3 -m commonwork release --repo OWNER/REPO 12
```

Reviewers should inspect the current PR head and its evidence before voting. Use `/vote yes FULL_SHA`, `/vote no FULL_SHA`, or `/vote abstain FULL_SHA` as the first line, followed by an explanation on a new line. `FULL_SHA` means the complete 40-character commit identifier. Use a new `/vote withdraw FULL_SHA` to remove your ballot explicitly. PR authors and bot accounts cannot vote; code changes require fresh votes.

Community support is advice to the maintainer. Maintainers retain the merge decision, check task fit and evidence, and apply whatever human approval and test requirements the repository has configured. Commonwork does not grant merge access or prevent multiple accounts from being controlled by one person.
