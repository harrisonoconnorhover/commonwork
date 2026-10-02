# Morning Handoff

## Finished

- Built Commonwork as a standalone local Git repository, separate from personal job-search files.
- Added idea/task forms, expiring task reservations, and work packets for contributors' own AI tools.
- Implemented PR comment ballots tied to the exact reviewed commit, one per eligible account, with quorum and explained votes.
- Added GitHub REST integration and metadata-only coordination workflows; contributor tests run separately with read-only permissions.
- Created an interactive offline demonstration using the actual voting and reservation functions.

## Try It

From this repository's root, run:

```sh
python3 -m commonwork demo
python3 -m http.server 8765 --bind 127.0.0.1 --directory demo-output
```

Open `http://127.0.0.1:8765/`. Switch between the reviewed revision and a new commit to see old ballots stop counting. Stop the server with Ctrl+C.

Read `README.md` for installation and contributor commands. The demo is synthetic; it makes no GitHub writes or AI calls.

## Checks

- 54 Python tests passed, including voting, reservations, API pagination, bot identity, event handling, CLI behavior, and offline demonstration.
- Python compilation, both workflows' `actionlint`, and staged diff whitespace checks passed.
- Browser verification: both revision buttons updated counts, commit identity, and explanation correctly. Desktop layout inspected; screenshot saved at `demo-output/preview.jpg`.
- Actual GitHub workflow execution and external writes were not tested.

## Decisions

- Volunteers contribute results using their own authorized accounts; no credentials or subscription capacity are pooled.
- Default community support needs three yes/no votes and at least two-thirds yes. Voting remains advisory; maintainers merge.
- GitHub provides shared coordination. This prototype adds no hosted worker fleet, automatic agent execution, or application database.

## Remaining

- Publish the MIT-licensed starter to [harrisonoconnorhover/commonwork](https://github.com/harrisonoconnorhover/commonwork). Publication is not yet verified.
- Install on the default branch and verify actual claims, releases, votes, edits/deletions, and changed-commit refresh.
- Configure repository review/check requirements and inspect GitHub's applicable Actions execution policy.
- Claims and ballots are reconstructed from current comments. Deletions can change history; account counts cannot prove independent people. This is not a tested large-community service.

## Review First

- `demo-output/index.html`: the contribution flow and vote behavior.
- `.github/workflows/commonwork.yml`: trusted code and limited write permissions.
- `README.md`: exact rules, installation, and known limits.
