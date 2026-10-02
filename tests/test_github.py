import unittest
from unittest.mock import Mock

from commonwork.github import GitHub, GitHubError, _GitHubRedirect, validate_repo


class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.client = GitHub("example/project", token="")

    def test_pagination_reads_more_than_one_hundred_comments(self):
        first = [{"id": number} for number in range(1, 101)]
        self.client.get = Mock(side_effect=[first, [{"id": 101}]])
        self.assertEqual(len(self.client.comments(8)), 101)
        self.assertEqual(self.client.get.call_args_list[1].args, ("issues/8/comments?per_page=100&page=2",))

    def test_later_page_failure_does_not_return_partial_tally_input(self):
        self.client.get = Mock(side_effect=[[{}] * 100, GitHubError("rate limited")])
        with self.assertRaises(GitHubError):
            self.client.comments(8)

    def test_human_marker_cannot_be_used_as_bot_summary(self):
        self.client.comment = Mock(return_value={"id": 99})
        self.client.request = Mock()
        fake = {"id": 20, "user": {"login": "github-actions[bot]", "type": "User"}, "body": "<!-- commonwork:vote-summary --> fake"}
        self.client.upsert_summary(8, [fake], "new body", "<!-- commonwork:vote-summary -->")
        self.client.comment.assert_called_once_with(8, "new body")
        self.client.request.assert_not_called()

    def test_existing_unchanged_bot_summary_causes_no_write(self):
        self.client.request = Mock()
        self.client.comment = Mock()
        old = {"id": 20, "user": {"login": "github-actions[bot]", "type": "Bot"}, "body": "<!-- commonwork:vote-summary --> same"}
        self.assertEqual(self.client.upsert_summary(8, [old], old["body"], "<!-- commonwork:vote-summary -->"), old)
        self.client.request.assert_not_called()
        self.client.comment.assert_not_called()

    def test_existing_bot_summary_is_updated_in_place(self):
        self.client.request = Mock()
        old = {"id": 20, "user": {"login": "github-actions[bot]", "type": "Bot"}, "body": "<!-- commonwork:vote-summary --> old"}
        self.client.upsert_summary(8, [old], "new body", "<!-- commonwork:vote-summary -->")
        self.client.request.assert_called_once_with("PATCH", "/repos/example/project/issues/comments/20", {"body": "new body"})

    def test_unauthenticated_write_is_stopped_before_network(self):
        self.client.opener = Mock()
        with self.assertRaises(GitHubError):
            self.client.comment(8, "/claim")
        self.client.opener.open.assert_not_called()

    def test_cross_host_redirect_never_forwards_authentication(self):
        with self.assertRaises(GitHubError):
            _GitHubRedirect().redirect_request(None, None, 302, "", {}, "https://example.com/steal")

    def test_repository_cannot_inject_api_paths(self):
        for invalid in ("../project", "owner/..", "owner/repo/extra", "owner/repo?query=x", "https://github.com/example/project"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_repo(invalid)


if __name__ == "__main__":
    unittest.main()
