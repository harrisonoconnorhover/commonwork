from copy import deepcopy
import unittest
from unittest.mock import Mock

from commonwork.reviews import read_review_packet, render_review_packet


HEAD = "a" * 40
BASE = "b" * 40
REPO = "community/project"


def pull_request(**updates):
    return {
        "number": 7, "title": "Improve task discovery", "body": "Task: #6\nAcceptance evidence: pending",
        "head": {"sha": HEAD}, "base": {"sha": BASE}, "state": "open", "draft": False,
        "user": {"login": "contributor"}, "changed_files": 1, **updates,
    }


def changed_file(**updates):
    return {"filename": "commonwork/board.py", "status": "modified", "additions": 4, "deletions": 2, **updates}


class ReviewPacketTests(unittest.TestCase):
    def test_packet_has_pinned_comparison_file_and_all_vote_commands(self):
        packet = render_review_packet(pull_request(), [changed_file()], REPO)
        self.assertIn(f"Exact head commit to review: `{HEAD}`", packet)
        self.assertIn(f"Exact target-base commit: `{BASE}`", packet)
        self.assertIn(f"https://github.com/{REPO}/compare/{BASE}...{HEAD}", packet)
        self.assertIn(f"https://github.com/{REPO}/blob/{HEAD}/commonwork/board.py", packet)
        for choice in ("yes", "no", "abstain", "withdraw"):
            self.assertIn(f"/vote {choice} {HEAD}", packet)
        self.assertIn("author-reported checks from checks you actually ran", packet)
        self.assertIn("not patches or full file contents", packet)
        self.assertNotIn("I reviewed", packet)

    def test_removed_and_renamed_files_link_to_correct_commits_and_encoded_paths(self):
        files = [
            changed_file(filename="old file?#.py", status="removed"),
            changed_file(filename="new/[name].py", status="renamed", previous_filename="old/[name].py"),
        ]
        packet = render_review_packet(pull_request(changed_files=2), files, REPO)
        self.assertIn(f"/blob/{BASE}/old%20file%3F%23.py", packet)
        self.assertIn(f"/blob/{HEAD}/new/%5Bname%5D.py", packet)
        self.assertIn(f"/blob/{BASE}/old/%5Bname%5D.py", packet)
        self.assertIn("renamed; +4 / -2", packet)

    def test_untrusted_text_cannot_break_out_of_fences_or_link_labels(self):
        body = "```\n# False instructions\n``````\n<script>bad()</script>"
        packet = render_review_packet(
            pull_request(title="Title ```", body=body),
            [changed_file(filename="x](https:evil)<script>.py")], REPO,
        )
        self.assertIn(f"```````text\n{body}\n```````", packet)
        self.assertIn("````text\nTitle ```\n````", packet)
        self.assertIn(r"x\]\(https:evil\)&lt;script&gt;\.py", packet)
        self.assertIn("x%5D%28https%3Aevil%29%3Cscript%3E.py", packet)

    def test_draft_closed_and_empty_description_are_explicit(self):
        draft = render_review_packet(pull_request(draft=True, body=None), [changed_file()], REPO)
        self.assertIn("Draft — feedback is welcome", draft)
        self.assertIn("No PR description supplied", draft)
        closed = render_review_packet(pull_request(state="closed"), [changed_file()], REPO)
        self.assertIn("Closed — historical review only; do not submit a new vote", closed)

    def test_incomplete_or_capped_file_list_is_rejected(self):
        for total in (2, 3001):
            with self.subTest(total=total), self.assertRaisesRegex(ValueError, "Incomplete changed-file list"):
                render_review_packet(pull_request(changed_files=total), [changed_file()], REPO)

    def test_invalid_paths_and_commit_shas_are_rejected(self):
        for path in ("../outside.py", "/outside.py", "a/../outside.py", ""):
            with self.subTest(path=path), self.assertRaises(ValueError):
                render_review_packet(pull_request(), [changed_file(filename=path)], REPO)
        with self.assertRaises(ValueError):
            render_review_packet(pull_request(head={"sha": "main"}), [changed_file()], REPO)

    def test_reader_fetches_paginated_files_and_only_reads(self):
        client = Mock(repo=REPO)
        client.get.side_effect = [pull_request(), pull_request()]
        client.list.return_value = [changed_file()]
        packet = read_review_packet(client, 7)
        self.assertIn("Commonwork review packet", packet)
        self.assertEqual(client.get.call_args_list[0].args, ("pulls/7",))
        self.assertEqual(client.get.call_args_list[1].args, ("pulls/7",))
        client.list.assert_called_once_with("pulls/7/files")
        client.comment.assert_not_called()
        client.request.assert_not_called()
        client.upsert_summary.assert_not_called()

    def test_reader_rejects_head_base_state_or_draft_change(self):
        for field, new_value in (("head", {"sha": "c" * 40}), ("base", {"sha": "d" * 40}),
                                 ("state", "closed"), ("draft", True)):
            with self.subTest(field=field):
                latest = deepcopy(pull_request())
                latest[field] = new_value
                client = Mock(repo=REPO)
                client.get.side_effect = [pull_request(), latest]
                client.list.return_value = [changed_file()]
                with self.assertRaisesRegex(RuntimeError, "PR changed while exporting"):
                    read_review_packet(client, 7)
                client.comment.assert_not_called()


if __name__ == "__main__":
    unittest.main()
