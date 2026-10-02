import copy
import unittest

from commonwork.votes import render_vote_summary, tally_votes


HEAD = "a" * 40
OLD = "b" * 40


def comment(comment_id, user_id, choice="yes", sha=HEAD, **overrides):
    value = {
        "id": comment_id,
        "body": f"/vote {choice} {sha}\nI reviewed the behavior.",
        "user": {"id": user_id, "login": f"reviewer-{user_id}", "type": "User"},
        "created_at": "2026-10-02T10:00:00Z",
        "updated_at": "2026-10-02T10:00:00Z",
        "html_url": "https://example.invalid/comment",
    }
    value.update(overrides)
    return value


class VoteTests(unittest.TestCase):
    def tally(self, comments, **policy):
        return tally_votes(comments, HEAD, 999, policy)

    def test_quorum_counts_yes_and_no_but_not_abstention(self):
        comments = [comment(1, 1), comment(2, 2), comment(3, 3, "abstain")]
        result = self.tally(comments)
        self.assertEqual((result["yes"], result["no"], result["abstain"]), (2, 0, 1))
        self.assertEqual(result["status"], "waiting")
        comments.append(comment(4, 4, "no"))
        self.assertEqual(self.tally(comments)["status"], "approved")

    def test_integer_threshold_and_strict_majority(self):
        comments = [comment(1, 1), comment(2, 2, "no")]
        result = self.tally(comments, quorum=2, approval_numerator=1, approval_denominator=2)
        self.assertEqual(result["status"], "changes_requested")
        comments.append(comment(3, 3))
        self.assertEqual(self.tally(comments)["status"], "approved")
        self.assertEqual(self.tally(comments, approval_numerator=3, approval_denominator=4)["status"], "changes_requested")

    def test_head_change_requires_new_votes(self):
        comments = [comment(1, 1), comment(2, 2), comment(3, 3)]
        result = tally_votes(comments, OLD, 999, {})
        self.assertEqual(result["status"], "waiting")
        self.assertEqual(result["yes"], 0)
        self.assertEqual(result["stale_count"], 3)

    def test_latest_updated_comment_wins_regardless_of_list_order(self):
        comments = [comment(12, 1), comment(2, 1, "no", updated_at="2026-10-02T11:00:00Z")]
        for ordering in (comments, list(reversed(comments))):
            result = self.tally(ordering, quorum=1)
            self.assertEqual((result["yes"], result["no"]), (0, 1))
            self.assertEqual(result["ballots"][0]["comment_id"], 2)
            self.assertEqual(result["excluded"]["superseded"], 1)

    def test_timestamp_tie_uses_comment_id_and_created_at_fallback(self):
        result = self.tally([comment(4, 1, "no"), comment(3, 1)], quorum=1)
        self.assertEqual(result["no"], 1)
        result = self.tally([
            comment(3, 1, "no", updated_at=None, created_at="2026-10-02T12:00:00Z"),
            comment(4, 1),
        ], quorum=1)
        self.assertEqual(result["no"], 1)

    def test_newer_stale_vote_does_not_revive_current_vote(self):
        result = self.tally([comment(1, 1), comment(2, 1, sha=OLD)], quorum=1)
        self.assertEqual(result["yes"], 0)
        self.assertEqual(result["stale_count"], 1)
        self.assertEqual(result["status"], "waiting")

    def test_latest_withdrawal_removes_vote_even_when_stale(self):
        for sha in (HEAD, OLD):
            result = self.tally([comment(1, 1), comment(2, 1, body=f"/vote withdraw {sha}")], quorum=1)
            self.assertEqual(result["yes"], 0)
            self.assertEqual(result["withdrawn_count"], 1)

    def test_deleted_and_edited_comments_have_no_ballot(self):
        self.assertEqual(self.tally([])["yes"], 0)
        edited = comment(1, 1, body="I removed my command.")
        self.assertEqual(self.tally([edited])["yes"], 0)
        # Snapshot semantics: deleting/editing the latest separate comment can
        # expose an older valid comment. An explicit withdrawal avoids this.
        result = self.tally([comment(1, 1), comment(2, 1, body="Removed")])
        self.assertEqual(result["yes"], 1)

    def test_author_bots_allowlist_and_identity_exclusion(self):
        comments = [
            comment(1, 999, user={"id": 999, "login": "renamed-author", "type": "User"}),
            comment(2, 2, user={"id": 2, "login": "machine", "type": "Bot"}),
            comment(3, 3, user={"id": 3, "login": "ci[bot]", "type": "User"}),
            comment(4, 4),
            comment(5, 5, user={"id": 5, "login": "Allowed", "type": "User"}),
        ]
        result = self.tally(comments, quorum=1, eligible_voters=["ALLOWED"])
        self.assertEqual(result["yes"], 1)
        self.assertEqual(result["excluded"]["author"], 1)
        self.assertEqual(result["excluded"]["bot"], 2)
        self.assertEqual(result["excluded"]["ineligible"], 1)
        self.assertEqual(result["eligible_voters"], ["allowed"])

    def test_same_account_renamed_cannot_vote_twice(self):
        comments = [comment(1, 1), comment(2, 1, "no", user={"id": 1, "login": "new-name", "type": "User"})]
        result = self.tally(comments, quorum=1)
        self.assertEqual((result["yes"], result["no"]), (0, 1))

    def test_only_explicit_github_user_identities_can_vote(self):
        comments = [
            comment(index, index, user={"id": index, "login": f"identity-{index}", "type": kind})
            for index, kind in enumerate(("Organization", "Mannequin", "user", "", None), 1)
        ]
        comments.append(comment(6, 6, user={"id": 6, "login": "missing-type"}))
        comments.append(comment(7, 7))
        result = self.tally(comments, quorum=1)
        self.assertEqual(result["yes"], 1)
        self.assertEqual(result["excluded"]["non_user"], 6)
        self.assertEqual(result["ballots"][0]["user_id"], 7)

    def test_commands_must_be_exact_first_line_and_include_explanation(self):
        invalid = [
            f"> /vote yes {HEAD}\nReason",
            f"Some context\n/vote yes {HEAD}\nReason",
            f"```\n/vote yes {HEAD}\nReason\n```",
            f" /vote yes {HEAD}\nReason",
            f"/vote yes {HEAD} \nReason",
            f"/vote yes {HEAD} extra\nReason",
            f"/vote YES {HEAD}\nReason",
            f"/vote  yes {HEAD}\nReason",
            f"/vote yes {HEAD[:7]}\nReason",
            f"/vote yes {HEAD}",
            f"/vote no {HEAD}\n  \n\t",
            f"/vote abstain {HEAD}",
            f"/vote yes {HEAD}\u2028Reason",
            f"/vote yes {HEAD}\vReason",
        ]
        for body in invalid:
            with self.subTest(body=body):
                self.assertEqual(self.tally([comment(1, 1, body=body)])["ballots"], [])
        result = self.tally([comment(1, 1, body=f"/vote yes {HEAD.upper()}\r\nReason")])
        self.assertEqual(result["yes"], 1)

    def test_invalid_newer_command_does_not_supersede_valid_vote(self):
        result = self.tally([comment(1, 1), comment(2, 1, body=f"/vote no {HEAD}")])
        self.assertEqual(result["yes"], 1)

    def test_invalid_policy_and_arguments_fail_clearly(self):
        for policy in ({"quorum": 0}, {"quorum": True}, {"quorum": 1.5}, {"approval_denominator": 0}, {"approval_numerator": 4}, {"eligible_voters": "bob"}, {"eligible_voters": ["unsafe<login>"]}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.tally([], **policy)
        with self.assertRaises(ValueError):
            tally_votes([], "short", 999, {})
        with self.assertRaises(ValueError):
            tally_votes([], HEAD, True, {})
        with self.assertRaises(TypeError):
            tally_votes({}, HEAD, 999, {})

    def test_summary_is_advisory_and_does_not_echo_reasons_or_urls(self):
        vote = comment(1, 1, body=f"/vote yes {HEAD}\n<script>unsafe reason</script>", html_url="javascript:bad")
        result = self.tally([vote], quorum=1)
        original = copy.deepcopy(result)
        summary = render_vote_summary(result)
        self.assertTrue(summary.startswith("<!-- commonwork:vote-summary -->"))
        self.assertIn(f"/vote yes {HEAD}", summary)
        self.assertIn("not merge permission", summary)
        self.assertIn("One GitHub account does not mean one person", summary)
        self.assertIn("rerun the tally", summary)
        self.assertNotIn("unsafe reason", summary)
        self.assertNotIn("javascript:", summary)
        self.assertNotIn("html_url", result["ballots"][0])
        self.assertEqual(result, original)
        result["ballots"].append({"login": "<script>", "choice": "yes"})
        self.assertNotIn("<script>", render_vote_summary(result))


if __name__ == "__main__":
    unittest.main()
