from datetime import datetime, timezone
import unittest

from commonwork.board import filter_rows, render_board_html, render_board_text
from commonwork.tasks import claim_state


NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
SHA = "a" * 40
REPO = "community/project"


def render(renderer, rows):
    return renderer(rows, REPO, generated_at=NOW, policy_source="GitHub default branch")


def task(number=7, **state):
    return {"number": number, "kind": "task", "title": "[Task] Keyboard navigation",
            "status": "available", "holder": None, "expires_at": None, **state}


def review(**fields):
    return {"number": 8, "kind": "review", "title": "Fix keyboard focus", "status": "waiting",
            "head_sha": SHA, "yes": 1, "no": 0, "abstain": 0, "decisive_votes": 1,
            "quorum": 3, "stale_count": 2, "draft": False, **fields}


class BoardTests(unittest.TestCase):
    def test_empty_snapshot_has_real_next_steps_and_time(self):
        for renderer in (render_board_text, render_board_html):
            with self.subTest(renderer=renderer.__name__):
                output = render(renderer, [])
                self.assertIn("2026-10-02 12:00:00 UTC", output)
                self.assertIn("GitHub default branch", output)
                self.assertIn("No matching", output)
                self.assertIn("https://github.com/community/project/issues/new?template=idea.yml", output)
                self.assertIn("https://github.com/community/project/issues/new?template=task.yml", output)

    def test_claimed_task_names_holder_and_expiry_without_inviting_another_claim(self):
        row = task(status="claimed", holder={"login": "river"}, expires_at="2026-10-03T10:00:00Z")
        for renderer in (render_board_text, render_board_html):
            with self.subTest(renderer=renderer.__name__):
                output = render(renderer, [row])
                self.assertIn("@river", output)
                self.assertIn("2026-10-03T10:00:00Z", output)
                self.assertIn("packet --repo community/project 7 --output work-packets/task-7.md", output)
                self.assertNotIn("claim --repo", output)

    def test_expired_claim_is_available_and_filter_does_not_mutate_rows(self):
        state = claim_state([{"id": 1, "body": "/claim", "user": {"id": 12, "login": "river", "type": "User"},
                              "created_at": "2026-10-01T10:00:00Z", "updated_at": "2026-10-01T10:00:00Z"}], NOW)
        expired = task(**state)
        held = task(9, status="claimed", holder={"login": "sage"}, expires_at="2026-10-03T10:00:00Z")
        rows = [expired, held, review()]
        self.assertEqual(filter_rows(rows, available=True), [expired])
        self.assertEqual(filter_rows(rows, kind="review"), [rows[2]])
        self.assertEqual(len(rows), 3)
        self.assertIn("claim --repo community/project 7", render(render_board_text, [expired]))

    def test_review_shows_exact_commit_counts_and_local_review_command(self):
        for renderer in (render_board_text, render_board_html):
            with self.subTest(renderer=renderer.__name__):
                output = render(renderer, [review()])
                self.assertIn(SHA, output)
                self.assertIn("1 yes · 0 no · 0 abstain", output)
                self.assertIn("1 of 3 decisive votes", output)
                self.assertIn("2 stale ballot(s)", output)
                self.assertIn("review --repo community/project 8 --output work-packets/review-8.md", output)
                self.assertIn("https://github.com/community/project/pull/8", output)
                self.assertNotIn("/vote yes", output)

    def test_draft_is_not_presented_as_merge_ready_despite_tally_support(self):
        for renderer in (render_board_text, render_board_html):
            with self.subTest(renderer=renderer.__name__):
                output = render(renderer, [review(draft=True, status="approved")])
                self.assertIn("Draft", output)
                self.assertIn("not ready for merge", output)

    def test_untrusted_values_are_inert_and_urls_are_constructed(self):
        hostile = task(title='<img src=x onerror="alert(1)">', url="javascript:alert(1)")
        output = render_board_html([hostile], REPO, generated_at=NOW, policy_source="</aside><script>alert(2)</script>")
        self.assertNotIn("<img", output)
        self.assertNotIn("<script>alert", output)
        self.assertNotIn("javascript:", output)
        self.assertIn("&lt;img", output)
        self.assertIn("https://github.com/community/project/issues/7", output)
        terminal = render(render_board_text, [task(title="hello\x1b[31m\nworld")])
        self.assertNotIn("\x1b", terminal)
        self.assertNotIn("\nworld", terminal)

    def test_html_filters_have_labels_and_do_not_load_network_assets(self):
        output = render(render_board_html, [task(), review()])
        for name in ("search", "kind", "available"):
            self.assertIn(f'id="{name}"', output)
        self.assertIn('for="search"', output)
        self.assertIn('for="kind"', output)
        self.assertIn('aria-live="polite"', output)
        self.assertNotIn("fetch(", output)
        self.assertNotIn("<script src=", output)
        self.assertNotIn("<link", output)

    def test_renderer_rejects_unsafe_link_inputs_and_naive_capture_time(self):
        with self.assertRaises(ValueError):
            render_board_html([], "owner/repo\" onclick=", generated_at=NOW, policy_source="fixture")
        with self.assertRaises(ValueError):
            render(render_board_html, [task(number="7/../../other")])
        with self.assertRaises(ValueError):
            render_board_text([], REPO, generated_at=datetime(2026, 10, 2), policy_source="fixture")
        with self.assertRaises(ValueError):
            filter_rows([], kind="invalid")


if __name__ == "__main__":
    unittest.main()
