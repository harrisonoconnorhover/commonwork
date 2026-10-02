import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from commonwork.coordinator import load_policy, read_repository_policy
from commonwork.github import GitHubError


SHA = "b" * 40


class PolicyTests(unittest.TestCase):
    def client(self, value):
        client = Mock(repo="community/project")
        client.request.return_value = {"default_branch": "release/stable"}
        client.get.side_effect = [
            {"sha": SHA},
            {"type": "file", "encoding": "base64", "content": base64.encodebytes(json.dumps(value).encode()).decode()},
        ]
        return client

    def test_remote_policy_is_read_at_exact_default_branch_commit(self):
        client = self.client({"quorum": 5, "claim_hours": 2})
        policy, source, sha = read_repository_policy(client)
        self.assertEqual((policy["quorum"], policy["claim_hours"], sha), (5, 2, SHA))
        self.assertEqual(policy["approval_denominator"], 3)
        self.assertIn("community/project/.commonwork/policy.json", source)
        self.assertIn(SHA, source)
        self.assertEqual([call.args[0] for call in client.get.call_args_list], [
            "commits/release%2Fstable", f"contents/.commonwork/policy.json?ref={SHA}",
        ])
        client.comment.assert_not_called()

    def test_invalid_remote_policy_does_not_silently_use_local_defaults(self):
        for value in ([], {"schema_version": 2}, {"quorum": 0}, {"claim_hours": 0}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_repository_policy(self.client(value))

    def test_missing_remote_policy_reports_error_instead_of_using_wrong_policy(self):
        client = self.client({})
        client.get.side_effect = [{"sha": SHA}, GitHubError("GitHub returned HTTP 404")]
        with self.assertRaisesRegex(GitHubError, "404"):
            read_repository_policy(client)

    def test_local_override_uses_same_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text('{"claim_hours": 6, "quorum": 4}')
            self.assertEqual(load_policy(path)["quorum"], 4)
            path.write_text('[]')
            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_policy(path)
