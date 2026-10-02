# Design decisions

These choices describe the local prototype built on October 2, 2026.

1. **GitHub is the shared workspace.** Ideas and tasks are issues, results are PRs, and coordination is visible in comments. Python 3.11+ and the standard library keep the starter runnable without an application server or package installation. See the handoff for the current remote installation status.

2. **Volunteers contribute work through their own accounts.** Exported packets are manual handoffs. Commonwork does not pool AI tokens, store provider credentials, launch agents, or promise that a provider permits transferring subscription capacity. Each volunteer chooses authorized tools, an environment, and a budget.

3. **Reservations use current comments.** The first valid human claim gets a 24-hour lease by default; only its holder can release it. Repeated claims do not renew an active lease. Edited commands are ignored and deleted comments alter history. Expiration is calculated at the next read/event; posted summaries can become stale between events.

4. **Votes express support for an exact commit.** The latest valid command per numeric account ID wins by update time and comment ID. Bots and the PR author are excluded. The default requires three decisive votes, at least two-thirds yes, and a strict yes majority. Withdrawal is explicit; edits/deletions can reveal older comments. Voting remains advisory because account counts do not establish independent people or authorize merging.

5. **The coordinator has a narrow write boundary.** Only trusted default-branch code handles the workflow token, event JSON is data, and PR code executes only in the separate read-only test workflow. The deployed default-branch policy controls bot summaries; local CLI policies do not. Live verification required both `issues: write` and `pull-requests: write` for the two comment surfaces; `contents` remains read-only. Manual dispatch provides refresh when automatic events are unavailable. See [GitHub's event-policy and security guidance](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target).

6. **Share a small, inspectable starting point.** The owner requested posting the result in the original Reddit discussion. The standalone starter uses the MIT License so others can inspect, adapt, and contribute. Real GitHub execution is recorded separately from fixture evidence; publication alone is not a successful multi-contributor trial.
