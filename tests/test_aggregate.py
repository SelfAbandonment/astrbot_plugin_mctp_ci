import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aggregate import AggregateEngine  # noqa: E402
from core import normalize_payload  # noqa: E402


def event(**overrides):
    data = {
        "repo": "MCTP-FE",
        "event": "ci",
        "status": "success",
        "title": "CI",
        "branch": "feat/x",
        "pr": "58",
        "actor": "Limor14514",
        "commit": "abc1234",
        "url": "https://example.test/pr/58",
    }
    data.update(overrides)
    return normalize_payload(data)


class AggregateTest(unittest.TestCase):
    def test_approval_is_buffered_until_merge(self):
        engine = AggregateEngine()
        self.assertIsNone(engine.ingest(event(event="pr_review", status="approved"), now=100))

        action = engine.ingest(event(event="pr_merge", status="merged"), now=101)
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.reason, "final")
        self.assertEqual(action.key, "pr:MCTP-FE#58")

        payload = engine.payload_for(action.key, action.reason)
        assert payload is not None
        self.assertEqual(payload["status"], "merged")
        self.assertEqual(payload["event"], "pr")
        self.assertIn("审核：通过", payload["details"])
        self.assertIn("合并：已合并", payload["details"])
        self.assertTrue(any("PR" in detail for detail in payload["details"]))

    def test_failure_alert_then_final(self):
        engine = AggregateEngine()
        failure = engine.ingest(
            event(event="ci", status="failure", title="CI 失败", url="https://example.test/run/1"),
            now=200,
        )
        assert failure is not None
        self.assertEqual(failure.reason, "failure")
        engine.finish(failure.key, failure.reason)
        self.assertIn(failure.key, engine.aggregates)

        final = engine.ingest(
            event(event="pr_merge", status="merged", url="https://example.test/pr/58"),
            now=201,
        )
        assert final is not None
        self.assertEqual(final.reason, "final")
        payload = engine.payload_for(final.key, final.reason)
        assert payload is not None
        self.assertEqual(payload["status"], "merged")
        self.assertIn("CI：失败 1 次", payload["details"])
        engine.finish(final.key, final.reason)
        self.assertNotIn(final.key, engine.aggregates)

    def test_duplicate_event_is_ignored(self):
        engine = AggregateEngine()
        payload = event(event="pr_review", status="approved")
        self.assertIsNone(engine.ingest(payload, now=1))
        self.assertIsNone(engine.ingest(payload, now=2))

    def test_deploy_is_separate_chain(self):
        engine = AggregateEngine()
        action = engine.ingest(
            event(event="deploy", status="success", pr="", title="生产部署完成"),
            now=300,
        )
        assert action is not None
        self.assertEqual(action.key, "deploy:MCTP-FE")
        payload = engine.payload_for(action.key, action.reason)
        assert payload is not None
        self.assertEqual(payload["event"], "deploy")

    def test_comment_is_ignored(self):
        engine = AggregateEngine()
        self.assertIsNone(engine.ingest(event(event="pr_comment", status="comment"), now=1))

    def test_state_survives_serialization(self):
        engine = AggregateEngine()
        engine.ingest(event(event="pr_review", status="approved"), now=100)
        action = engine.ingest(event(event="pr_merge", status="merged"), now=101)
        assert action is not None

        restored = AggregateEngine.from_dict(engine.to_dict())
        pending = restored.pending_actions(101)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].key, action.key)
        self.assertEqual(pending[0].reason, "final")

    def test_main_pr_waits_then_combines_with_deploy(self):
        engine = AggregateEngine(release_wait=600)
        fe = engine.ingest(
            event(
                event="pr_merge",
                status="merged",
                repo="MCTP-FE",
                pr="72",
                base_ref="main",
                commit="fe12345",
            ),
            now=100,
        )
        api = engine.ingest(
            event(
                event="pr_merge",
                status="merged",
                repo="MCTP-API",
                pr="68",
                base_ref="main",
                commit="api6789",
            ),
            now=101,
        )
        assert fe is not None and api is not None
        self.assertEqual(fe.delay, 600)
        self.assertEqual(api.delay, 600)
        self.assertFalse(engine.aggregates[fe.key].terminal)
        self.assertFalse(engine.aggregates[api.key].terminal)

        deploy = engine.ingest(
            event(
                event="deploy",
                status="success",
                repo="MCTP",
                pr="",
                commit="",
                release_key="fe12345:api6789",
                title="生产部署完成",
            ),
            now=102,
        )
        assert deploy is not None
        self.assertEqual(deploy.key, "release:fe12345:api6789")
        self.assertNotIn(fe.key, engine.aggregates)
        self.assertNotIn(api.key, engine.aggregates)
        payload = engine.payload_for(deploy.key, deploy.reason)
        assert payload is not None
        self.assertEqual(payload["status"], "success")
        self.assertIn("MCTP-FE PR #72 已合并", payload["details"])
        self.assertIn("MCTP-API PR #68 已合并", payload["details"])


if __name__ == "__main__":
    unittest.main()
