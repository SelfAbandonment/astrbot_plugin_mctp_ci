import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (  # noqa: E402
    STATUS_META,
    build_card_html,
    build_plain_text,
    merge_targets,
    normalize_payload,
    remove_targets,
    sample_payload,
    status_meta,
    test_payload,
    verify_token,
)


class NormalizePayloadTest(unittest.TestCase):
    def test_defaults_and_unknown_status(self):
        payload = normalize_payload({"title": "hello", "status": "boom"})
        self.assertEqual(payload["status"], "info")
        self.assertEqual(payload["repo"], "MCTP")
        self.assertEqual(payload["title"], "hello")
        self.assertEqual(payload["details"], [])
        self.assertEqual(len(payload["id"]), 16)

    def test_truncates_and_limits_details(self):
        payload = normalize_payload(
            {
                "title": "x" * 300,
                "details": [f"line {i}" for i in range(20)],
            }
        )
        self.assertEqual(len(payload["title"]), 120)
        self.assertEqual(len(payload["details"]), 8)

    def test_string_details_become_list(self):
        payload = normalize_payload({"title": "t", "details": "one"})
        self.assertEqual(payload["details"], ["one"])

    def test_non_dict_payload(self):
        payload = normalize_payload("nope")
        self.assertEqual(payload["title"], "CI 通知")


class CardTest(unittest.TestCase):
    def test_card_escapes_html(self):
        payload = normalize_payload(
            {
                "title": "<script>alert(1)</script>",
                "subtitle": "<b>x</b>",
                "details": ["<img src=x onerror=alert(1)>"],
            }
        )
        html = build_card_html(payload)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)

    def test_card_uses_status_accent(self):
        payload = normalize_payload({"title": "fail", "status": "failure"})
        html = build_card_html(payload)
        self.assertIn(STATUS_META["failure"]["accent"], html)
        self.assertIn("失败", html)

    def test_all_statuses_have_meta(self):
        for status in STATUS_META:
            meta = status_meta(status)
            self.assertIn("accent", meta)
            self.assertIn("label", meta)

    def test_sample_payload_renders(self):
        payload = sample_payload()
        html = build_card_html(payload)
        self.assertIn("单元测试失败", html)
        self.assertIn("MCTP-FE", html)

    def test_test_payload_is_neutral_success(self):
        payload = test_payload()
        self.assertEqual(payload["status"], "success")
        self.assertIn("链路正常", payload["title"])
        self.assertEqual(payload["details"][0].startswith("触发方式"), True)


class PlainTextTest(unittest.TestCase):
    def test_plain_text_contains_key_lines(self):
        text = build_plain_text(sample_payload())
        self.assertIn("[失败]", text)
        self.assertIn("分支：feat/announcement-pin", text)
        self.assertIn("https://github.com/", text)


class TokenTest(unittest.TestCase):
    def test_token_compare(self):
        self.assertTrue(verify_token("abc", "abc"))
        self.assertFalse(verify_token("abc", "abd"))
        self.assertFalse(verify_token("", "abc"))
        self.assertFalse(verify_token("abc", ""))


class TargetsTest(unittest.TestCase):
    def test_merge_dedupes_and_keeps_order(self):
        merged = merge_targets(
            ["aiocqhttp:GroupMessage:1", "aiocqhttp:FriendMessage:2"],
            ["aiocqhttp:FriendMessage:2", "aiocqhttp:GroupMessage:3"],
        )
        self.assertEqual(
            merged,
            [
                "aiocqhttp:GroupMessage:1",
                "aiocqhttp:FriendMessage:2",
                "aiocqhttp:GroupMessage:3",
            ],
        )

    def test_remove_clears_both_sources(self):
        configured, stored = remove_targets(
            ["aiocqhttp:GroupMessage:1", "aiocqhttp:FriendMessage:2"],
            ["aiocqhttp:FriendMessage:2", "aiocqhttp:GroupMessage:3"],
            ["aiocqhttp:FriendMessage:2"],
        )
        self.assertEqual(configured, ["aiocqhttp:GroupMessage:1"])
        self.assertEqual(stored, ["aiocqhttp:GroupMessage:3"])

    def test_invalid_targets_ignored(self):
        self.assertEqual(merge_targets(["bad", "  "], [None]), [])


if __name__ == "__main__":
    unittest.main()
