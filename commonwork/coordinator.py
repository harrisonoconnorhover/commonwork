"""Coordinate metadata-only GitHub tasks and advisory PR ballots."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .github import GitHub, positive_number
from .tasks import claim_state, render_claim_summary
from .votes import tally_votes, render_vote_summary


DEFAULT_POLICY = {
    "schema_version": 1,
    "quorum": 3,
    "approval_numerator": 2,
    "approval_denominator": 3,
    "eligible_voters": [],
    "claim_hours": 24,
}


def load_policy(path: str | Path = ".commonwork/policy.json") -> dict:
    return validate_policy(json.loads(Path(path).read_text(encoding="utf-8")))


def validate_policy(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Policy must be a JSON object.")
    policy = DEFAULT_POLICY | value
    if policy.get("schema_version") != 1:
        raise ValueError("Unsupported policy schema_version; expected 1.")
    hours = policy.get("claim_hours")
    if type(hours) is not int or not 1 <= hours <= 168:
        raise ValueError("claim_hours must be an integer from 1 through 168.")
    # Validate voting configuration even when handling a task, before any writes.
    tally_votes([], "0" * 40, 1, policy)
    return policy


def default_branch_sha(client: GitHub) -> str:
    repository = client.request("GET", f"/repos/{client.repo}")
    branch = quote(repository["default_branch"], safe="")
    sha = client.get(f"commits/{branch}")["sha"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("GitHub returned an invalid default-branch commit.")
    return sha.lower()


def read_repository_policy(client: GitHub) -> tuple[dict, str, str]:
    """Read deployed policy and pin its source to one default-branch commit."""
    sha = default_branch_sha(client)
    source = f"{client.repo}/.commonwork/policy.json at {sha}"
    contents = client.get(f"contents/.commonwork/policy.json?ref={sha}")
    if contents.get("type") != "file" or contents.get("encoding") != "base64":
        raise ValueError("The repository policy must be a JSON file readable through GitHub.")
    encoded = "".join(contents["content"].split())
    policy = validate_policy(json.loads(base64.b64decode(encoded, validate=True).decode("utf-8")))
    return policy, source, sha


def task_issue(issue: dict) -> bool:
    return "pull_request" not in issue and issue.get("title", "").startswith("[Task] ")


def command_comment(comment: dict, is_pr: bool) -> bool:
    if comment.get("user", {}).get("type") != "User":
        return False
    body = comment.get("body") or ""
    first = body.splitlines()[0].strip() if body.splitlines() else ""
    return first.startswith("/vote ") if is_pr else first in {"/claim", "/release"}


def event_numbers(event: dict, event_name: str) -> list[int]:
    """Only react to relevant human input; bot writes must not loop."""
    if event_name == "issue_comment":
        issue = event.get("issue", {})
        is_pr = "pull_request" in issue
        if not (is_pr or task_issue(issue)):
            return []
        comment = event.get("comment", {})
        if comment.get("user", {}).get("type") != "User":
            return []
        # An edit can REMOVE a command: always reconcile human edits/deletes.
        if event.get("action") in {"edited", "deleted"} or command_comment(comment, is_pr):
            return [positive_number(issue["number"])]
        return []
    if event_name == "pull_request_target":
        return [positive_number(event["pull_request"]["number"])]
    if event_name == "issues":
        issue = event.get("issue", {})
        return [positive_number(issue["number"])] if task_issue(issue) else []
    if event_name == "workflow_dispatch":
        value = event.get("inputs", {}).get("number", "")
        return [positive_number(value)] if value else []
    raise ValueError(f"Unsupported event: {event_name}")


def sync_one(client: GitHub, number: int, policy: dict, *, now=None) -> dict:
    number = positive_number(number)
    issue = client.get(f"issues/{number}")
    comments = client.comments(number)
    if "pull_request" in issue:
        pr = client.get(f"pulls/{number}")
        head_sha = pr["head"]["sha"]
        result = tally_votes(comments, head_sha, pr["user"]["id"], policy)
        body = render_vote_summary(result)
        if pr.get("state") != "open":
            body += "\n\n**This PR is closed.** The tally is historical and cannot authorize a merge.\n"
        elif pr.get("draft"):
            body += "\n\n**Draft PR:** finish the contribution before requesting a merge.\n"
        # Avoid publishing an already-known stale head. Event refresh handles later races.
        latest = client.get(f"pulls/{number}")
        if latest["head"]["sha"] != head_sha:
            raise RuntimeError("PR changed during tallying. Re-run the coordinator for a fresh tally.")
        client.upsert_summary(number, comments, body, "<!-- commonwork:vote-summary -->")
        return {"number": number, "kind": "pull_request", **result}
    if not task_issue(issue):
        return {"number": number, "kind": "issue", "status": "ignored"}
    result = claim_state(comments, now or datetime.now(timezone.utc), policy["claim_hours"])
    body = render_claim_summary(result)
    if issue.get("state") != "open":
        body += "\n\n**This task is closed.** Do not begin new work without reopening it.\n"
    client.upsert_summary(number, comments, body, "<!-- commonwork:claim-summary -->")
    return {"number": number, "kind": "task", **result}


def board(client: GitHub, policy: dict, *, now=None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = []
    for issue in client.list("issues?state=open&sort=created&direction=asc"):
        if "pull_request" in issue:
            kind = "review"
            pr = client.get(f"pulls/{issue['number']}")
            state = tally_votes(client.comments(issue["number"]), pr["head"]["sha"], pr["user"]["id"], policy)
            state["draft"] = bool(pr.get("draft"))
        elif task_issue(issue):
            kind = "task"
            state = claim_state(client.comments(issue["number"]), now, policy["claim_hours"])
        elif issue.get("title", "").startswith("[Idea] "):
            kind, state = "idea", {"status": "discussion"}
        else:
            continue
        rows.append({"number": issue["number"], "title": issue["title"], "kind": kind, "url": issue["html_url"], **state})
    return rows


def safe_terminal(text: str, *, multiline: bool = False) -> str:
    """Strip control sequences from community-provided text before terminal output."""
    pattern = r"[\x00-\x08\x0b-\x1f\x7f-\x9f]" if multiline else r"[\x00-\x1f\x7f-\x9f]"
    return re.sub(pattern, " ", text)
