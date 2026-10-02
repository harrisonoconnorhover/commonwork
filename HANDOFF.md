# Morning Handoff

## Finished

- Added a searchable board of real GitHub work, with available-task and contribution-type filters, reservation holders/expiry, PR vote counts, and next-step commands. Export text, JSON, or standalone HTML.
- Added PR review packets with pinned commits, changed-file links, acceptance checklists, and explained voting options. Changed revisions or incomplete file lists stop the export.
- CLI commands now use the target repository's deployed policy by default. Task packets put the assignment first.
- Reworked the newcomer quickstart and opened [pilot task #3](https://github.com/harrisonoconnorhover/commonwork/issues/3); its coordinator summary is live.
- The [MIT repository](https://github.com/harrisonoconnorhover/commonwork) retains advisory voting, own-account contributions, and trusted default-branch coordination.

## Try It

From the repository root, with Python 3.11+:

```sh
python3 -m commonwork board --repo harrisonoconnorhover/commonwork --format html --output demo-output/board.html
python3 -m commonwork review --repo harrisonoconnorhover/commonwork 2 --output work-packets/review-2.md
```

Open `demo-output/board.html`. Rerun its export for fresh data. PR #2 is a closed historical example; do not vote there. Use `board --available` to find work and follow the README before claiming.

## Checks

- All 79 automated tests passed locally, including policy pinning, review races/incomplete lists, board escaping/filtering, and existing coordination behavior.
- Offline demo generation, Python compilation, workflow lint (`actionlint`), and `git diff --check` passed.
- Real GitHub reads verified deployed policy, task #3 availability and work-packet export, and PR #2 review export with its exact head and closed status.
- Browser checks passed for search, availability/type filters, empty results, desktop layout, and 390px layout without horizontal overflow.
- Task #3 received its live bot summary. Earlier [single-account smoke tests](https://github.com/harrisonoconnorhover/commonwork/pull/2) covered claims/releases, author-vote exclusion, and new-head summary updates.

## Decisions

- Board pages are dated, read-only local snapshots; no hosted service or background refresh.
- Remote policy governs default CLI calculations; explicit local overrides never alter bot policy.
- Review exports prepare human-controlled work, without running code or certifying author claims.

## Remaining

- Complete the outside-contributor pilot; multi-person collaboration and abuse resistance remain unverified.
- Configure repository review/check requirements before accepting production contributions.
- Account votes do not establish independent people; editable/deletable comments are not immutable history.

## Review First

1. README quickstart and pilot task #3.
2. `commonwork/board.py` and `commonwork/reviews.py`.
3. Remote-policy integration in `commonwork/__main__.py` and `commonwork/coordinator.py`.
