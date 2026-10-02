"""Run with python3 -m commonwork; explicit verbs make external writes visible."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

from .coordinator import board, event_numbers, load_policy, safe_terminal, sync_one, task_issue
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
        ("claim", "POST a 24-hour task reservation request to GitHub"),
        ("release", "POST a request to release your task reservation"),
        ("vote", "POST your explained ballot on the current PR head"),
        ("tally", "Read and compute a PR tally without posting anything"),
    ]:
        command = sub.add_parser(name, help=description)
        command.add_argument("--repo", required=True, help="OWNER/REPOSITORY")
        command.add_argument("--policy", default=".commonwork/policy.json")
        if name != "board":
            command.add_argument("number", type=positive_number)
        if name == "packet":
            command.add_argument("--output", help="Save Markdown here (otherwise print it)")
        if name == "vote":
            command.add_argument("choice", choices=["yes", "no", "abstain", "withdraw"])
            command.add_argument("--sha", required=True, help="Full 40-character commit you actually reviewed")
            command.add_argument("--reason", default="", help="Required for yes, no, or abstain")
    workflow = sub.add_parser("sync-event", help="GitHub Actions: reconcile metadata and post bot summaries")
    workflow.add_argument("--policy", default=".commonwork/policy.json")
    return root


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
        policy = load_policy(args.policy)
        if args.command == "sync-event":
            if os.environ.get("GITHUB_ACTIONS") != "true":
                raise ValueError("sync-event is reserved for the installed GitHub Actions workflow.")
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
            numbers = event_numbers(event, os.environ["GITHUB_EVENT_NAME"])
            if not numbers:
                print("No relevant human command or task/PR update.")
                return 0
            client = GitHub(os.environ["GITHUB_REPOSITORY"], token=os.environ.get("GITHUB_TOKEN", ""))
            for number in numbers:
                result = sync_one(client, number, policy)
                print(json.dumps({"number": number, "kind": result["kind"], "status": result["status"]}))
            return 0
        client = GitHub(args.repo)
        if args.command == "board":
            for row in board(client, policy):
                print(f"#{row['number']:<5} {row['kind']:<7} {row['status']:<18} {safe_terminal(row['title'])}")
            return 0
        if args.command in {"vote", "tally"}:
            pr = client.get(f"pulls/{args.number}")
            sha = pr["head"]["sha"]
            if args.command == "tally":
                print(json.dumps(tally_votes(client.comments(args.number), sha, pr["user"]["id"], policy), indent=2))
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
            repository = client.request("GET", f"/repos/{client.repo}")
            branch = quote(repository["default_branch"], safe="")
            sha = client.get(f"commits/{branch}")["sha"]
            packet = render_work_packet(issue, client.repo, sha, policy["claim_hours"])
            if args.output:
                path = Path(args.output)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(packet)
                print(f"Work packet saved: {path.resolve()}")
            else:
                print(safe_terminal(packet, multiline=True) if sys.stdout.isatty() else packet)
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
