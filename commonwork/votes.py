"""Commit-specific, advisory voting over GitHub pull-request comments.

An account is identified by its numeric GitHub user id. The optional allowlist
uses mutable GitHub logins, so it is a convenience restriction, not proof of a
person's identity. One account does not imply one person.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


_SHA = re.compile(r"[0-9a-fA-F]{40}")
_COMMAND = re.compile(r"/vote (yes|no|abstain|withdraw) ([0-9a-fA-F]{40})")
_LOGIN = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,37}[a-zA-Z0-9])?")


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _policy_values(policy: dict) -> tuple[int, int, int, set[str]]:
    if not isinstance(policy, dict):
        raise TypeError("policy must be a dictionary")
    quorum = _positive_int(policy.get("quorum", 3), "quorum")
    numerator = _positive_int(policy.get("approval_numerator", 2), "approval_numerator")
    denominator = _positive_int(policy.get("approval_denominator", 3), "approval_denominator")
    if numerator > denominator:
        raise ValueError("approval_numerator cannot exceed approval_denominator")
    voters = policy.get("eligible_voters", [])
    if not isinstance(voters, list) or any(
        not isinstance(login, str) or not _LOGIN.fullmatch(login) for login in voters
    ):
        raise ValueError("eligible_voters must be a list of GitHub logins")
    return quorum, numerator, denominator, {login.lower() for login in voters}


def _timestamp(comment: dict) -> datetime:
    for field in ("updated_at", "created_at"):
        value = comment.get(field)
        if not isinstance(value, str):
            continue
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if timestamp.tzinfo is not None:
            return timestamp.astimezone(timezone.utc)
    # Missing timestamps do not make an otherwise well-formed vote disappear.
    # GitHub supplies timestamps; the id is a deterministic fallback for fixtures.
    return datetime.min.replace(tzinfo=timezone.utc)


def tally_votes(comments: list[dict], head_sha: str, author_id: int, policy: dict) -> dict:
    """Count each eligible account's latest valid command on the exact PR head.

    A newer valid command for another commit supersedes an older current-head
    vote. A latest withdrawal removes that account's vote even if its SHA is
    stale. Invalid commands are ignored. Deleted comments are absent from the
    supplied snapshot; editing a comment to remove the command also removes it
    from consideration. An older *separate* valid comment can then be latest.
    """
    if not isinstance(comments, list):
        raise TypeError("comments must be a list")
    if not isinstance(head_sha, str) or not _SHA.fullmatch(head_sha):
        raise ValueError("head_sha must be a full 40-character hexadecimal commit SHA")
    _positive_int(author_id, "author_id")
    quorum, numerator, denominator, eligible = _policy_values(policy)
    head_sha = head_sha.lower()
    excluded = {"invalid": 0, "bot": 0, "non_user": 0, "author": 0, "ineligible": 0, "superseded": 0}
    latest: dict[int, tuple[tuple[datetime, int], dict]] = {}

    for comment in comments:
        if not isinstance(comment, dict):
            excluded["invalid"] += 1
            continue
        body = comment.get("body")
        if not isinstance(body, str):
            excluded["invalid"] += 1
            continue
        # Only the first physical line is a command. Markdown quotations,
        # embedded examples, leading whitespace, and trailing text cannot vote.
        first_line, newline, explanation = body.partition("\n")
        if newline and first_line.endswith("\r"):
            first_line = first_line[:-1]  # Accept ordinary CRLF comments.
        match = _COMMAND.fullmatch(first_line)
        if not match:
            excluded["invalid"] += 1
            continue
        choice, commit = match.groups()
        if choice != "withdraw" and not explanation.strip():
            excluded["invalid"] += 1
            continue
        user = comment.get("user")
        comment_id = comment.get("id")
        if not isinstance(user, dict):
            excluded["invalid"] += 1
            continue
        user_id = user.get("id")
        login = user.get("login")
        if (
            isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1
            or isinstance(comment_id, bool) or not isinstance(comment_id, int) or comment_id < 1
        ):
            excluded["invalid"] += 1
            continue
        if str(user.get("type", "")).lower() == "bot" or (
            isinstance(login, str) and login.lower().endswith("[bot]")
        ):
            excluded["bot"] += 1
            continue
        if user.get("type") != "User":
            excluded["non_user"] += 1
            continue
        if user_id == author_id:
            excluded["author"] += 1
            continue
        if not isinstance(login, str) or not _LOGIN.fullmatch(login):
            excluded["invalid"] += 1
            continue
        if eligible and login.lower() not in eligible:
            excluded["ineligible"] += 1
            continue
        ballot = {
            "user_id": user_id,
            "login": login,
            "choice": choice,
            "comment_id": comment_id,
            "head_sha": commit.lower(),
        }
        rank = (_timestamp(comment), comment_id)
        if user_id in latest:
            excluded["superseded"] += 1
        if user_id not in latest or rank > latest[user_id][0]:
            latest[user_id] = (rank, ballot)

    ballots = []
    stale_count = 0
    withdrawn_count = 0
    for _, ballot in latest.values():
        if ballot["choice"] == "withdraw":
            withdrawn_count += 1
        elif ballot["head_sha"] != head_sha:
            stale_count += 1
        else:
            ballots.append(ballot)
    ballots.sort(key=lambda ballot: (ballot["login"].lower(), ballot["user_id"]))
    yes = sum(ballot["choice"] == "yes" for ballot in ballots)
    no = sum(ballot["choice"] == "no" for ballot in ballots)
    abstain = sum(ballot["choice"] == "abstain" for ballot in ballots)
    decisive = yes + no
    if decisive < quorum:
        status = "waiting"
    elif yes > no and yes * denominator >= decisive * numerator:
        status = "approved"
    else:
        status = "changes_requested"
    return {
        "head_sha": head_sha,
        "status": status,
        "yes": yes,
        "no": no,
        "abstain": abstain,
        "quorum": quorum,
        "decisive_votes": decisive,
        "approval_numerator": numerator,
        "approval_denominator": denominator,
        "threshold": f"at least {numerator}/{denominator} yes among yes + no, and strictly more yes than no",
        "ballots": ballots,
        "stale_count": stale_count,
        "withdrawn_count": withdrawn_count,
        "excluded": excluded,
        "eligible_voters": sorted(eligible),
    }


def render_vote_summary(result: dict) -> str:
    """Render a safe bot comment without contributor reasons or URLs."""
    if not isinstance(result, dict):
        raise TypeError("result must be a tally dictionary")
    sha = result.get("head_sha")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError("result head_sha must be a full commit SHA")
    status_labels = {
        "waiting": "Waiting for quorum",
        "approved": "Community support reached",
        "changes_requested": "Community support threshold not reached",
    }
    if result.get("status") not in status_labels:
        raise ValueError("result status is invalid")
    counts = {}
    for key in ("yes", "no", "abstain", "stale_count", "withdrawn_count"):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"result {key} must be a nonnegative integer")
        counts[key] = value
    quorum, numerator, denominator, eligible = _policy_values(result)
    lines = [
        "<!-- commonwork:vote-summary -->",
        "## Commonwork community vote",
        "",
        f"**{status_labels[result['status']]}** — advisory support only; this is not merge permission.",
        "",
        f"Commit: `{sha.lower()}`",
        "",
        "| Yes | No | Abstain | Required yes + no |",
        "| ---: | ---: | ---: | ---: |",
        f"| {counts['yes']} | {counts['no']} | {counts['abstain']} | {quorum} |",
        "",
        f"Approval needs at least {numerator}/{denominator} yes among yes + no and strictly more yes than no. Abstentions do not count toward quorum.",
        "",
        "### Vote in this pull request",
        "",
        "Post a new comment with exactly one of these commands on the first line:",
        "",
        "```text",
        f"/vote yes {sha.lower()}",
        f"/vote no {sha.lower()}",
        f"/vote abstain {sha.lower()}",
        f"/vote withdraw {sha.lower()}",
        "```",
        "",
        "For yes, no, or abstain, add a nonempty explanation on a new line. Withdrawal needs no explanation.",
        "",
        "Each account's latest valid command wins by comment update time, then comment id. Only GitHub User accounts can vote; bots and the PR author cannot vote. Votes for another commit are stale; a newer stale vote does not revive an older vote. A latest withdrawal removes the account's vote.",
        "",
        "Deleted comments and comments edited to remove their command are absent; an older separate valid comment may then become latest. Use withdraw to remove your ballot explicitly.",
        "",
    ]
    if eligible:
        lines.append("Voting is restricted to configured GitHub logins. Logins can change and are not permanent identity guarantees.")
        lines.append("")
    lines += [
        "One GitHub account does not mean one person; account votes are not proof of independent human review. Maintainers retain merge decisions and required checks still apply.",
        "",
        "After code changes, rerun the tally and vote again for the new head commit.",
        "",
        f"Excluded latest ballots: {counts['stale_count']} stale; {counts['withdrawn_count']} withdrawn.",
    ]
    ballots = result.get("ballots", [])
    if not isinstance(ballots, list):
        raise ValueError("result ballots must be a list")
    safe_ballots = []
    for ballot in ballots:
        if not isinstance(ballot, dict):
            continue
        login, choice = ballot.get("login"), ballot.get("choice")
        if isinstance(login, str) and _LOGIN.fullmatch(login) and choice in ("yes", "no", "abstain"):
            safe_ballots.append(f"- `{login}`: **{choice}**")
    if safe_ballots:
        lines += ["", "### Current ballots", ""] + safe_ballots
    return "\n".join(lines) + "\n"
