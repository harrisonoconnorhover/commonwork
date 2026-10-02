from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from commonwork.__main__ import main
from commonwork.coordinator import DEFAULT_POLICY


SHA = "a" * 40


class CliTests(unittest.TestCase):
    def run_cli(self, arguments, client):
        output, error = io.StringIO(), io.StringIO()
        with patch("commonwork.__main__.GitHub", return_value=client), \
             patch("commonwork.__main__.load_policy", return_value=dict(DEFAULT_POLICY)), \
             patch("commonwork.__main__.read_repository_policy", return_value=(dict(DEFAULT_POLICY), "remote policy at " + SHA, SHA)), \
             redirect_stdout(output), redirect_stderr(error):
            result = main(arguments)
        return result, output.getvalue(), error.getvalue()

    def test_board_filters_and_json_include_snapshot_provenance_without_writes(self):
        client = Mock(repo="community/project")
        rows = [
            {"number": 7, "title": "[Task] Open", "kind": "task", "status": "available"},
            {"number": 8, "title": "[Task] Taken", "kind": "task", "status": "claimed"},
            {"number": 9, "title": "Review", "kind": "review", "status": "waiting"},
        ]
        with patch("commonwork.__main__.board", return_value=rows):
            result, output, error = self.run_cli([
                "board", "--repo", client.repo, "--available", "--format", "json",
            ], client)
        self.assertEqual((result, error), (0, ""))
        snapshot = json.loads(output)
        self.assertEqual([row["number"] for row in snapshot["items"]], [7])
        self.assertEqual(snapshot["policy_source"], "remote policy at " + SHA)
        self.assertIn("generated_at", snapshot)
        client.comment.assert_not_called()

    def test_explicit_local_policy_does_not_fetch_remote_policy(self):
        client = Mock(repo="community/project")
        with patch("commonwork.__main__.GitHub", return_value=client), \
             patch("commonwork.__main__.load_policy", return_value=dict(DEFAULT_POLICY)) as local, \
             patch("commonwork.__main__.read_repository_policy") as remote, \
             patch("commonwork.__main__.board", return_value=[]), redirect_stdout(io.StringIO()) as output:
            result = main(["board", "--repo", client.repo, "--policy", "custom.json", "--format", "json"])
        self.assertEqual(result, 0)
        local.assert_called_once_with("custom.json")
        remote.assert_not_called()
        self.assertIn("Local override", json.loads(output.getvalue())["policy_source"])

    def test_review_writes_only_local_packet_and_needs_no_policy_file(self):
        client = Mock(repo="community/project")
        with tempfile.TemporaryDirectory() as directory, \
             patch("commonwork.__main__.GitHub", return_value=client), \
             patch("commonwork.__main__.load_policy", side_effect=AssertionError("No local policy needed")), \
             patch("commonwork.__main__.read_repository_policy", side_effect=AssertionError("No policy needed")), \
             patch("commonwork.reviews.read_review_packet", return_value="# Review fixture") as packet, \
             redirect_stdout(io.StringIO()):
            path = Path(directory) / "review.md"
            result = main(["review", "--repo", client.repo, "7", "--output", str(path)])
            self.assertEqual(path.read_text(), "# Review fixture")
        self.assertEqual(result, 0)
        packet.assert_called_once_with(client, 7)
        client.comment.assert_not_called()

    def test_packet_uses_same_commit_as_remote_policy(self):
        client = Mock(repo="community/project")
        client.get.return_value = {"number": 7, "title": "[Task] Fix", "body": "Acceptance", "state": "open"}
        result, output, error = self.run_cli(["packet", "--repo", client.repo, "7"], client)
        self.assertEqual((result, error), (0, ""))
        self.assertIn(f"Exact base commit: `{SHA}`", output)
        self.assertIn("remote policy at " + SHA, output)
        client.get.assert_called_once_with("issues/7")
        client.comment.assert_not_called()

    def pr_client(self):
        client = Mock()
        client.get.return_value = {"head": {"sha": SHA}, "user": {"id": 10}, "state": "open"}
        client.comment.return_value = {"html_url": "https://github.com/community/project/pull/7#issuecomment-99"}
        return client

    def test_vote_requires_the_explicit_reviewed_commit_before_any_client_is_created(self):
        error = io.StringIO()
        with patch("commonwork.__main__.GitHub") as github, redirect_stderr(error), self.assertRaises(SystemExit) as stopped:
            main(["vote", "--repo", "community/project", "7", "yes", "--reason", "Reviewed."])
        self.assertEqual(stopped.exception.code, 2)
        self.assertIn("--sha", error.getvalue())
        github.assert_not_called()

    def test_vote_against_a_different_head_does_not_post(self):
        client = self.pr_client()
        result, output, error = self.run_cli([
            "vote", "--repo", "community/project", "7", "yes", "--sha", "b" * 40, "--reason", "Reviewed.",
        ], client)
        self.assertEqual(result, 1)
        self.assertIn("changed since your review", error)
        self.assertEqual(output, "")
        client.comment.assert_not_called()

    def test_successful_vote_posts_exact_commit_and_explanation(self):
        client = self.pr_client()
        result, output, error = self.run_cli([
            "vote", "--repo", "community/project", "7", "yes", "--sha", SHA,
            "--reason", "  Checked keyboard navigation.\nFocus remains visible.  ",
        ], client)
        self.assertEqual(result, 0)
        self.assertEqual(error, "")
        client.comment.assert_called_once_with(7, f"/vote yes {SHA}\n\nChecked keyboard navigation.\nFocus remains visible.")
        self.assertIn("Ballot posted:", output)
        self.assertIn("determine eligibility", output)

    def test_claim_reports_a_request_instead_of_falsely_confirming_a_lease(self):
        client = Mock()
        client.get.return_value = {"number": 7, "title": "[Task] Improve keyboard navigation", "state": "open"}
        client.comment.return_value = {"html_url": "https://github.com/community/project/issues/7#issuecomment-99"}
        result, output, error = self.run_cli(["claim", "--repo", "community/project", "7"], client)
        self.assertEqual(result, 0)
        self.assertEqual(error, "")
        client.comment.assert_called_once_with(7, "/claim")
        self.assertIn("Request posted:", output)
        self.assertIn("confirm the reservation result", output)
        self.assertNotIn("Reservation confirmed", output)

    def test_offline_demo_needs_no_token_and_expires_votes_after_a_head_change(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
             patch("commonwork.__main__.GitHub", side_effect=AssertionError("Offline demo must not create a GitHub client")) as github, \
             patch("commonwork.github.GitHub._token", side_effect=AssertionError("Offline demo must not look up credentials")), \
             patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Offline demo must not access the network")), \
             redirect_stdout(io.StringIO()):
            result = main(["demo", "--output", directory])
            results = json.loads((Path(directory) / "results.json").read_text())
            self.assertEqual(result, 0)
            github.assert_not_called()
            self.assertEqual(results["mode"], "offline_fixture")
            self.assertEqual(results["claim"]["holder"]["login"], "river")
            self.assertEqual(results["current_revision"]["yes"], 2)
            self.assertEqual(results["current_revision"]["no"], 1)
            self.assertEqual(results["current_revision"]["status"], "approved")
            self.assertEqual(results["new_revision"]["yes"], 0)
            self.assertEqual(results["new_revision"]["no"], 0)
            self.assertEqual(results["new_revision"]["stale_count"], 3)
            self.assertNotEqual(results["new_revision"]["status"], "approved")
            self.assertTrue((Path(directory) / "index.html").is_file())
            self.assertTrue((Path(directory) / "work-packet.md").is_file())


if __name__ == "__main__":
    unittest.main()
