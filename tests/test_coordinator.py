from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

from commonwork.coordinator import DEFAULT_POLICY, event_numbers, sync_one
from commonwork.github import GitHub


SHA = "a" * 40
OTHER_SHA = "b" * 40
MARKER = "<!-- commonwork:vote-summary -->"


def human(body, number=1):
    return {
        "id": number,
        "body": body,
        "user": {"id": 20, "login": "reviewer", "type": "User"},
        "created_at": "2026-10-02T10:00:00Z",
        "updated_at": "2026-10-02T10:00:00Z",
    }


class FakeGitHub:
    """Only metadata reads and captured summary writes; never a network client."""

    def __init__(self, issue=None, comments=None, head_shas=None):
        self.issue = issue if issue is not None else {
            "number": 7, "title": "A contribution", "state": "open", "pull_request": {},
        }
        self.snapshot = comments if comments is not None else []
        self.head_shas = iter(head_shas or [SHA, SHA])
        self.writes = []

    def get(self, path):
        if path == "issues/7":
            return self.issue
        if path == "pulls/7":
            return {"number": 7, "head": {"sha": next(self.head_shas)}, "user": {"id": 10}, "state": "open"}
        raise AssertionError(f"Unexpected metadata read: {path}")

    def comments(self, number):
        assert number == 7
        return self.snapshot

    def upsert_summary(self, number, comments, body, marker):
        self.writes.append({"number": number, "body": body, "marker": marker})


class CoordinatorTests(unittest.TestCase):
    def test_bot_summary_changes_do_not_dispatch_another_sync(self):
        for action in ("created", "edited", "deleted"):
            event = {
                "action": action,
                "issue": {"number": 7, "pull_request": {}},
                "comment": {"body": MARKER, "user": {"login": "github-actions[bot]", "type": "Bot"}},
            }
            with self.subTest(action=action):
                self.assertEqual(event_numbers(event, "issue_comment"), [])

    def test_human_edits_removing_ballots_and_deletes_refresh_the_tally(self):
        original = human(f"/vote yes {SHA}\nReviewed the acceptance criteria.")
        before = sync_one(FakeGitHub(comments=[original]), 7, DEFAULT_POLICY)
        self.assertEqual(before["yes"], 1)
        edited = {**original, "body": "I am withdrawing my review for now.", "updated_at": "2026-10-02T11:00:00Z"}
        for action, comments in (("edited", [edited]), ("deleted", [])):
            event = {"action": action, "issue": {"number": 7, "pull_request": {}}, "comment": edited}
            with self.subTest(action=action):
                self.assertEqual(event_numbers(event, "issue_comment"), [7])
                client = FakeGitHub(comments=comments)
                result = sync_one(client, 7, DEFAULT_POLICY)
                self.assertEqual(result["yes"], 0)
                self.assertEqual(len(client.writes), 1)
                self.assertEqual(client.writes[0]["marker"], MARKER)

    def test_head_changing_during_reconciliation_prevents_summary_write(self):
        client = FakeGitHub(comments=[human(f"/vote yes {SHA}\nReviewed.")], head_shas=[SHA, OTHER_SHA])
        with self.assertRaisesRegex(RuntimeError, "changed during tallying"):
            sync_one(client, 7, DEFAULT_POLICY)
        self.assertEqual(client.writes, [])

    def test_only_task_issues_accept_claims_and_receive_claim_summaries(self):
        now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
        for title, expected in (("[Task] Improve keyboard navigation", [7]), ("[Idea] Improve accessibility", [])):
            issue = {"number": 7, "title": title, "state": "open"}
            event = {"action": "created", "issue": issue, "comment": human("/claim")}
            with self.subTest(title=title):
                self.assertEqual(event_numbers(event, "issue_comment"), expected)
                self.assertEqual(event_numbers({"action": "opened", "issue": issue}, "issues"), expected)
                client = FakeGitHub(issue=issue, comments=[human("/claim")])
                result = sync_one(client, 7, DEFAULT_POLICY, now=now)
                self.assertEqual(result["status"], "claimed" if expected else "ignored")
                self.assertEqual(len(client.writes), len(expected))

    def test_dispatch_requires_a_positive_number_and_supported_event(self):
        self.assertEqual(event_numbers({"inputs": {"number": "7"}}, "workflow_dispatch"), [7])
        self.assertEqual(event_numbers({"inputs": {}}, "workflow_dispatch"), [])
        self.assertEqual(event_numbers({"pull_request": {"number": 7}}, "pull_request_target"), [7])
        for value in ("0", "-1", "abc", "7; arbitrary-command"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                event_numbers({"inputs": {"number": value}}, "workflow_dispatch")
        with self.assertRaisesRegex(ValueError, "Unsupported event"):
            event_numbers({}, "push")

    def test_human_marker_cannot_impersonate_the_actions_summary(self):
        client = GitHub("community/project", token="fixture-only")
        client.request = Mock(return_value={"id": 99})
        comments = [human(MARKER + "\nForged tally")]
        client.upsert_summary(7, comments, MARKER + "\nReal tally", MARKER)
        client.request.assert_called_once_with(
            "POST", "/repos/community/project/issues/7/comments", {"body": MARKER + "\nReal tally"},
        )


if __name__ == "__main__":
    unittest.main()
