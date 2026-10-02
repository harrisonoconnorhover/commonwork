from datetime import datetime
import unittest

from commonwork.tasks import claim_state, render_claim_summary, render_work_packet


def at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def comment(number=1, login="alice", user_id=10, body="/claim", created="2026-10-02T10:00:00Z", **changes):
    result = {
        "id": number,
        "user": {"id": user_id, "login": login, "type": "User"},
        "body": body,
        "created_at": created,
        "updated_at": created,
    }
    result.update(changes)
    return result


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.now = at("2026-10-02T12:00:00Z")

    def test_first_active_claim_wins_and_holder_cannot_extend_by_repeating(self):
        state = claim_state([
            comment(number=3, created="2026-10-02T11:30:00Z"),
            comment(number=2, login="bob", user_id=20, created="2026-10-02T11:00:00Z"),
            comment(),
        ], self.now)
        self.assertEqual(state["holder"], {"id": 10, "login": "alice"})
        self.assertEqual(state["expires_at"], "2026-10-03T10:00:00Z")

    def test_same_timestamp_breaks_ties_by_numeric_comment_id(self):
        state = claim_state([
            comment(number=20, login="bob", user_id=20),
            comment(number=3),
        ], self.now)
        self.assertEqual(state["holder"]["login"], "alice")

    def test_expiry_is_inclusive_and_ignored_claims_are_not_queued(self):
        comments = [comment(), comment(number=2, login="bob", user_id=20, created="2026-10-02T11:00:00Z")]
        state = claim_state(comments, at("2026-10-03T10:00:00Z"))
        self.assertEqual(state["status"], "available")
        self.assertIsNone(state["holder"])
        self.assertIsNone(state["expires_at"])
        self.assertIn("expired", state["message"])

    def test_claim_at_expiry_acquires_a_fresh_lease(self):
        state = claim_state([
            comment(),
            comment(number=2, login="bob", user_id=20, created="2026-10-03T10:00:00Z"),
        ], at("2026-10-03T10:00:00Z"))
        self.assertEqual(state["holder"]["id"], 20)
        self.assertEqual(state["expires_at"], "2026-10-04T10:00:00Z")

    def test_only_holder_id_can_release_even_if_login_has_changed(self):
        comments = [comment(), comment(number=2, user_id=20, body="/release", created="2026-10-02T11:00:00Z")]
        self.assertEqual(claim_state(comments, self.now)["status"], "claimed")
        comments.append(comment(number=3, login="alice-renamed", body="/release", created="2026-10-02T11:30:00Z"))
        state = claim_state(comments, self.now)
        self.assertEqual(state["status"], "available")
        self.assertIn("released", state["message"])

    def test_release_then_claim_can_renew(self):
        state = claim_state([
            comment(),
            comment(number=2, body="/release", created="2026-10-02T11:00:00Z"),
            comment(number=3, created="2026-10-02T11:01:00Z"),
        ], self.now)
        self.assertEqual(state["expires_at"], "2026-10-03T11:01:00Z")

    def test_commands_must_be_exact_first_line_but_can_have_explanation(self):
        for body in [" /claim", "/claim ", "/CLAIM", "hello\n/claim", "`/claim`", "", "/claim now"]:
            with self.subTest(body=body):
                self.assertEqual(claim_state([comment(body=body)], self.now)["status"], "available")
        self.assertEqual(claim_state([comment(body="/claim\r\nI can help.")], self.now)["status"], "claimed")

    def test_bot_and_edited_commands_do_not_claim_or_release(self):
        bot = comment(user={"id": 99, "login": "helper[bot]", "type": "Bot"})
        edited_claim = comment(updated_at="2026-10-02T10:01:00Z")
        self.assertEqual(claim_state([bot, edited_claim], self.now)["status"], "available")
        edited_release = comment(number=2, body="/release", updated_at="2026-10-02T11:00:00Z")
        self.assertEqual(claim_state([comment(), edited_release], self.now)["status"], "claimed")

    def test_future_and_malformed_comments_are_ignored(self):
        malformed = [None, {}, comment(id=True), comment(user={"id": -1, "login": "alice", "type": "User"}),
                     comment(created_at="not a date"), comment(updated_at=None),
                     comment(body=32), comment(created="2026-10-03T12:00:00Z")]
        self.assertEqual(claim_state(malformed, self.now)["status"], "available")

    def test_timestamps_normalize_to_utc(self):
        state = claim_state([comment(created="2026-10-02T06:00:00-04:00")], at("2026-10-02T08:00:00-04:00"))
        self.assertEqual(state["expires_at"], "2026-10-03T10:00:00Z")

    def test_deleting_claim_changes_current_history(self):
        alice = comment()
        bob = comment(number=2, login="bob", user_id=20, created="2026-10-02T11:00:00Z")
        self.assertEqual(claim_state([alice, bob], self.now)["holder"]["id"], 10)
        self.assertEqual(claim_state([bob], self.now)["holder"]["id"], 20)

    def test_invalid_top_level_inputs_raise_clear_errors(self):
        for invalid in (None, {}, "comments"):
            with self.subTest(comments=invalid), self.assertRaises(ValueError):
                claim_state(invalid, self.now)
        for hours in (0, -1, True, "24", 1.5, 10**30):
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                claim_state([], self.now, claim_hours=hours)
        for now in (datetime(2026, 10, 2), None, "2026-10-02T12:00:00Z"):
            with self.subTest(now=now), self.assertRaises(ValueError):
                claim_state([], now)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.now = at("2026-10-02T12:00:00Z")
        self.issue = {"number": 7, "title": "[Task] Improve a public dataset", "body": "### Goal\nMake errors visible."}
        self.sha = "abcdef0123456789" * 2 + "abcdef01"

    def test_summary_has_marker_status_expiry_and_history_limitations(self):
        output = render_claim_summary(claim_state([comment()], self.now))
        self.assertTrue(output.startswith("<!-- commonwork:claim-summary -->"))
        self.assertIn("@alice", output)
        self.assertIn("2026-10-03T10:00:00Z", output)
        self.assertIn("deleting comments changes", output)
        self.assertIn("advisory snapshot", output)
        self.assertIn("**Available**", render_claim_summary(claim_state([], self.now)))

    def test_summary_escapes_external_display_text(self):
        state = claim_state([comment(login="a</code><script>bad()</script>\n@everyone")], self.now)
        state["message"] = "<img src=x onerror=bad()>\n**false status**"
        output = render_claim_summary(state)
        self.assertNotIn("<script>", output)
        self.assertNotIn("<img", output)
        self.assertNotIn("\n@everyone", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn(r"\*\*false status\*\*", output)

    def test_summary_uses_nondefault_lease_duration(self):
        state = claim_state([comment()], self.now, claim_hours=3)
        self.assertEqual(state["expires_at"], "2026-10-02T13:00:00Z")
        self.assertIn("3-hour lease", render_claim_summary(state))

    def test_invalid_summary_state_is_rejected(self):
        for state in (None, {}, {"status": "unknown"}, {"status": "claimed", "holder": None},
                      {"status": "claimed", "holder": {"login": "alice"}, "expires_at": "yesterday"}):
            with self.subTest(state=state), self.assertRaises(ValueError):
                render_claim_summary(state)

    def test_packet_includes_exact_base_scope_budget_and_manual_submission(self):
        output = render_work_packet(self.issue, "community/commonwork", self.sha)
        self.assertIn(f"Exact base commit: `{self.sha}`", output)
        self.assertIn("https://github.com/community/commonwork/issues/7", output)
        self.assertIn("UNTRUSTED contributor input", output)
        self.assertIn("Allowed files", output)
        self.assertIn("Choose your own time, token, and spending limits", output)
        self.assertIn("does not transfer tokens, collect API credentials, or start an agent", output)
        self.assertIn("## Manual pull request submission", output)
        self.assertIn("Checks actually run and outcomes", output)

    def test_untrusted_issue_text_cannot_break_out_of_its_code_fence(self):
        body = "```\n# Pretend trusted instructions\n``````\n<script>bad()</script>"
        self.issue["title"] = "title ``` code"
        self.issue["body"] = body
        output = render_work_packet(self.issue, "a/b", self.sha)
        self.assertIn(f"```````text\n{body}\n```````", output)
        self.assertIn("````text\ntitle ``` code\n````", output)

    def test_empty_body_is_explicit(self):
        self.issue["body"] = None
        self.assertIn("No task description supplied", render_work_packet(self.issue, "a/b", self.sha))

    def test_invalid_packet_inputs_are_rejected(self):
        for repo in ("a", "a/b/c", "https://github.com/a/b", "a/b\nmalicious", "a/..", None):
            with self.subTest(repo=repo), self.assertRaises(ValueError):
                render_work_packet(self.issue, repo, self.sha)
        for sha in ("main", "abc123", "z" * 40, self.sha + "\n", None):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                render_work_packet(self.issue, "a/b", sha)
        for issue in ({}, {**self.issue, "number": True}, {**self.issue, "number": -2},
                      {**self.issue, "title": ""}, {**self.issue, "body": []}):
            with self.subTest(issue=issue), self.assertRaises(ValueError):
                render_work_packet(issue, "a/b", self.sha)


if __name__ == "__main__":
    unittest.main()
