"""Run with python3 -m commonwork; explicit verbs make external writes visible."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .coordinator import (
    board, default_branch_sha, event_numbers, load_policy, read_repository_policy,
    safe_terminal, sync_one, task_issue,
)
from .github import GitHub, GitHubError, positive_number
from .tasks import render_work_packet
from .votes import tally_votes


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Coordinate volunteer AI work through GitHub.")
    sub = root.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Run an offline example; no accounts, network, or AI usage")
    demo.add_argument("--output", default="demo-output")
    for name, description in [
        ("board", "Read open ideas, tasks, and PR ballots"),
        ("packet", "Export a task for your own AI tool; does not claim or execute it"),
        ("review", "Export a PR review packet pinned to the current commit; no execution"),
        ("claim", "POST a task reservation request to GitHub"),
        ("release", "POST a request to release your task reservation"),
        ("vote", "POST your explained ballot on the current PR head"),
        ("tally", "Read and compute a PR tally without posting anything"),
    ]:
        command = sub.add_parser(name, help=description)
        command.add_argument("--repo", required=True, help="OWNER/REPOSITORY")
        if name != "review":
            command.add_argument("--policy", help="Use a local policy for this command; defaults to the target repository's deployed policy")
        if name != "board":
            command.add_argument("number", type=positive_number)
        if name in {"packet", "review"}:
            command.add_argument("--output", help="Save Markdown here (otherwise print it)")
        if name == "board":
            command.add_argument("--kind", choices=["all", "idea", "task", "review"], default="all")
            command.add_argument("--available", action="store_true", help="Show only tasks without an active reservation")
            command.add_argument("--format", choices=["text", "json", "html"], default="text")
            command.add_argument("--output", help="Save the snapshot here (otherwise print it)")
        if name == "vote":
            command.add_argument("choice", choices=["yes", "no", "abstain", "withdraw"])
            command.add_argument("--sha", required=True, help="Full 40-character commit you actually reviewed")
            command.add_argument("--reason", default="", help="Required for yes, no, or abstain")
    workflow = sub.add_parser("sync-event", help="GitHub Actions: reconcile metadata and post bot summaries")
    workflow.add_argument("--policy", default=".commonwork/policy.json")
    return root


def write_output(value: str, output: str | None, label: str) -> None:
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        print(f"{label} saved: {path.resolve()}")
    else:
        print(safe_terminal(value, multiline=True) if sys.stdout.isatty() else value)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import run_demo
            output = run_demo(Path(args.output))
            print(f"Offline demo created: {output.resolve()}")
            print("Task claimed by river; current PR has 2 yes / 1 no: community support.")
            print("After a new commit: 0 current votes; fresh reviews needed.")
            return 0
        if args.command == "sync-event":
            if os.environ.get("GITHUB_ACTIONS") != "true":
                raise ValueError("sync-event is reserved for the installed GitHub Actions workflow.")
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
            numbers = event_numbers(event, os.environ["GITHUB_EVENT_NAME"])
            if not numbers:
                print("No relevant human command or task/PR update.")
                return 0
            policy = load_policy(args.policy)
            client = GitHub(os.environ["GITHUB_REPOSITORY"], token=os.environ.get("GITHUB_TOKEN", ""))
            for number in numbers:
                result = sync_one(client, number, policy)
                print(json.dumps({"number": number, "kind": result["kind"], "status": result["status"]}))
            return 0
        if args.command == "board" and args.available and args.kind not in {"all", "task"}:
            raise ValueError("--available can only be combined with --kind task or all.")
        client = GitHub(args.repo)
        if args.command == "review":
            from .reviews import read_review_packet
            write_output(read_review_packet(client, args.number), args.output, "Review packet")
            return 0
        if args.policy:
            policy = load_policy(args.policy)
            policy_source = f"Local override: {args.policy}; deployed bot policy is unchanged"
            policy_sha = None
        else:
            policy, policy_source, policy_sha = read_repository_policy(client)
        if args.command == "board":
            from .board import filter_rows, render_board_html, render_board_text
            generated_at = datetime.now(timezone.utc)
            rows = filter_rows(board(client, policy, now=generated_at), kind=args.kind, available=args.available)
            if args.format == "json":
                rendered = json.dumps({
                    "repository": client.repo, "generated_at": generated_at.isoformat(),
                    "policy_source": policy_source, "items": rows,
                }, indent=2)
            else:
                render = render_board_html if args.format == "html" else render_board_text
                rendered = render(rows, client.repo, generated_at=generated_at, policy_source=policy_source)
            write_output(rendered, args.output, "Board snapshot")
            return 0
        if args.command in {"vote", "tally"}:
            pr = client.get(f"pulls/{args.number}")
            sha = pr["head"]["sha"]
            if args.command == "tally":
                result = tally_votes(client.comments(args.number), sha, pr["user"]["id"], policy)
                print(json.dumps({**result, "policy_source": policy_source}, indent=2))
                return 0
            if pr.get("state") != "open":
                raise ValueError("This pull request is closed.")
            if args.sha.lower() != sha.lower():
                raise ValueError("The PR changed since your review. Review its current head before voting.")
            if args.choice != "withdraw" and not args.reason.strip():
                raise ValueError("Provide --reason explaining what you reviewed.")
            body = f"/vote {args.choice} {sha}\n\n{args.reason.strip()}".rstrip()
            result = client.comment(args.number, body)
            print(f"Ballot posted: {result['html_url']}")
            print("The coordinator will determine eligibility and update the advisory tally.")
            return 0
        issue = client.get(f"issues/{args.number}")
        if not task_issue(issue):
            raise ValueError("Choose a task issue with a title beginning '[Task] '.")
        if issue.get("state") != "open":
            raise ValueError("This task is closed.")
        if args.command == "packet":
            sha = policy_sha or default_branch_sha(client)
            packet = render_work_packet(issue, client.repo, sha, policy["claim_hours"], policy_source=policy_source)
            write_output(packet, args.output, "Work packet")
            return 0
        result = client.comment(args.number, "/claim" if args.command == "claim" else "/release")
        print(f"Request posted: {result['html_url']}")
        print("Read the coordinator's task summary to confirm the reservation result.")
        return 0
    except (GitHubError, ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"Commonwork: {safe_terminal(str(error))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
