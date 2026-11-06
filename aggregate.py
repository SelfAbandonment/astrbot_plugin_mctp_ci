"""按聚合链归并 CI/PR/部署事件，避免每个事件单独发一张图。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MAX_EVENTS = 80
FAILURE_DELAY = 3.0
FINAL_DELAY = 5.0
DEPLOY_DELAY = 3.0


def _text(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[:limit]


def _event_key(payload: dict[str, Any]) -> str:
    event = _text(payload.get("event"), 30).lower()
    repo = _text(payload.get("repo"), 40) or "MCTP"
    pr = _text(payload.get("pr"), 20)
    if event == "deploy":
        return f"deploy:{repo}"
    if pr:
        return f"pr:{repo}#{pr}"
    if event == "ci":
        branch = _text(payload.get("branch"), 80) or "unknown"
        commit = _text(payload.get("commit"), 12) or "unknown"
        return f"ci:{repo}:{branch}:{commit}"
    return f"event:{repo}:{event}"


@dataclass
class Aggregate:
    key: str
    kind: str
    repo: str
    pr: str = ""
    branch: str = ""
    actor: str = ""
    commit: str = ""
    url: str = ""
    title: str = ""
    status: str = "info"
    stages: dict[str, str] = field(default_factory=dict)
    details: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    first_at: float = 0.0
    last_at: float = 0.0
    version: int = 0
    terminal: bool = False
    failure_count: int = 0
    failure_alerted: bool = False
    flush_at: float | None = None
    flush_reason: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Aggregate:
        fields = {
            "key",
            "kind",
            "repo",
            "pr",
            "branch",
            "actor",
            "commit",
            "url",
            "title",
            "status",
            "stages",
            "details",
            "event_ids",
            "first_at",
            "last_at",
            "version",
            "terminal",
            "failure_count",
            "failure_alerted",
            "flush_at",
            "flush_reason",
        }
        values = {key: data[key] for key in fields if key in data}
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "repo": self.repo,
            "pr": self.pr,
            "branch": self.branch,
            "actor": self.actor,
            "commit": self.commit,
            "url": self.url,
            "title": self.title,
            "status": self.status,
            "stages": self.stages,
            "details": self.details,
            "event_ids": self.event_ids,
            "first_at": self.first_at,
            "last_at": self.last_at,
            "version": self.version,
            "terminal": self.terminal,
            "failure_count": self.failure_count,
            "failure_alerted": self.failure_alerted,
            "flush_at": self.flush_at,
            "flush_reason": self.flush_reason,
        }


@dataclass
class AggregateAction:
    key: str
    version: int
    delay: float
    reason: str


class AggregateEngine:
    """内存状态；持久化和定时由插件层负责。"""

    def __init__(self) -> None:
        self.aggregates: dict[str, Aggregate] = {}

    @classmethod
    def from_dict(cls, data: Any) -> AggregateEngine:
        engine = cls()
        if not isinstance(data, dict):
            return engine
        for key, raw in data.items():
            if not isinstance(raw, dict):
                continue
            try:
                engine.aggregates[key] = Aggregate.from_dict(raw)
            except (TypeError, ValueError):
                continue
        return engine

    def to_dict(self) -> dict[str, Any]:
        return {key: agg.to_dict() for key, agg in self.aggregates.items()}

    def prune(self, now: float, max_age: float = 6 * 3600) -> None:
        """清理长期没有终态的缓存链，避免审核后一直不合并造成泄漏。"""
        for key, agg in list(self.aggregates.items()):
            if not agg.terminal and now - agg.last_at > max_age:
                self.aggregates.pop(key, None)

    def pending_actions(self, now: float) -> list[AggregateAction]:
        self.prune(now)
        actions = []
        for agg in self.aggregates.values():
            if agg.flush_at is None:
                continue
            actions.append(
                AggregateAction(
                    key=agg.key,
                    version=agg.version,
                    delay=max(0.0, agg.flush_at - now),
                    reason=agg.flush_reason,
                )
            )
        return actions

    def _schedule(self, agg: Aggregate, now: float, delay: float, reason: str) -> AggregateAction:
        agg.flush_at = now + delay
        agg.flush_reason = reason
        return AggregateAction(agg.key, agg.version, delay, reason)

    def ingest(self, payload: dict[str, Any], now: float | None = None) -> AggregateAction | None:
        now = float(now if now is not None else datetime.now().timestamp())
        self.prune(now)
        event = _text(payload.get("event"), 30).lower()
        status = _text(payload.get("status"), 20).lower()
        if event == "pr_comment":
            return None
        if event not in {"ci", "pr", "pr_review", "pr_merge", "deploy", "lighthouse", "contract"}:
            return None
        key = _event_key(payload)
        agg = self.aggregates.get(key)
        if agg is None:
            kind = "deploy" if event == "deploy" else ("pr" if payload.get("pr") else "ci")
            agg = Aggregate(
                key=key,
                kind=kind,
                repo=_text(payload.get("repo"), 40) or "MCTP",
                pr=_text(payload.get("pr"), 20),
                branch=_text(payload.get("branch"), 80),
                actor=_text(payload.get("actor"), 80),
                commit=_text(payload.get("commit"), 12),
                url=_text(payload.get("url"), 300),
                title=_text(payload.get("title"), 120),
                first_at=now,
                last_at=now,
            )
            self.aggregates[key] = agg

        event_id = _text(payload.get("id"), 80)
        if event_id and event_id in agg.event_ids:
            return None

        agg.version += 1
        agg.last_at = now
        agg.title = _text(payload.get("title"), 120) or agg.title
        agg.url = _text(payload.get("url"), 300) or agg.url
        agg.actor = _text(payload.get("actor"), 80) or agg.actor
        agg.commit = _text(payload.get("commit"), 12) or agg.commit
        agg.branch = _text(payload.get("branch"), 80) or agg.branch
        for detail in payload.get("details") or []:
            text = _text(detail, 120)
            if text and text not in agg.details:
                agg.details.append(text)
        agg.details = agg.details[-8:]
        if event_id:
            agg.event_ids.append(event_id)
            agg.event_ids = agg.event_ids[-MAX_EVENTS:]

        if event == "deploy":
            agg.kind = "deploy"
            agg.status = status if status in {"success", "failure"} else "info"
            agg.terminal = True
            return self._schedule(agg, now, DEPLOY_DELAY, "final")

        if event == "pr_merge" or status == "merged":
            agg.status = "merged"
            agg.stages["merge"] = "已合并"
            agg.terminal = True
            return self._schedule(agg, now, FINAL_DELAY, "final")

        if status == "failure":
            agg.status = "failure"
            agg.failure_count += 1
            agg.stages["ci"] = f"失败 {agg.failure_count} 次"
            if not agg.failure_alerted:
                return self._schedule(agg, now, FAILURE_DELAY, "failure")
            return self._pending_action(agg, now)

        if event == "pr_review" or status == "approved":
            agg.stages["review"] = "通过"
        elif status == "success":
            agg.stages["ci"] = "通过"
        elif status == "warning":
            agg.stages["ci"] = "警告"
        else:
            agg.details.append(f"{event}: {status or 'unknown'}")
            agg.details = agg.details[-8:]

        return self._pending_action(agg, now)

    def _pending_action(self, agg: Aggregate, now: float) -> AggregateAction | None:
        if agg.flush_at is None:
            return None
        return AggregateAction(
            key=agg.key,
            version=agg.version,
            delay=max(0.0, agg.flush_at - now),
            reason=agg.flush_reason,
        )

    def payload_for(self, key: str, reason: str) -> dict[str, Any] | None:
        agg = self.aggregates.get(key)
        if agg is None:
            return None
        if agg.kind == "deploy":
            status = agg.status if agg.status in {"success", "failure"} else "info"
            title = agg.title or f"{agg.repo} 部署通知"
            event = "deploy"
        elif reason == "failure":
            status = "failure"
            title = f"{agg.repo} PR #{agg.pr} CI 失败" if agg.pr else f"{agg.repo} CI 失败"
            event = "ci"
        else:
            status = "merged" if agg.status == "merged" else agg.status
            title = f"{agg.repo} PR #{agg.pr} 已合并" if agg.pr else f"{agg.repo} CI 通知"
            event = "pr" if agg.pr else "ci"

        details = self._details(agg)
        subtitle = "聚合链路"
        if agg.branch:
            subtitle += f" · {agg.branch}"
        return {
            "repo": agg.repo,
            "event": event,
            "status": status,
            "title": title,
            "subtitle": subtitle,
            "branch": agg.branch,
            "pr": agg.pr,
            "actor": agg.actor,
            "commit": agg.commit,
            "url": agg.url,
            "details": details,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def _details(self, agg: Aggregate) -> list[str]:
        details: list[str] = []
        ci = agg.stages.get("ci")
        if ci:
            details.append(f"CI：{ci}")
        review = agg.stages.get("review")
        if review:
            details.append(f"审核：{review}")
        merge = agg.stages.get("merge")
        if merge:
            details.append(f"合并：{merge}")
        if agg.kind == "pr":
            details.append("部署：不适用（PR 聚合）")
        elif agg.kind == "deploy":
            details.append("部署：完成" if agg.status == "success" else "部署：失败")
        if len(agg.event_ids) > 1:
            details.append(f"聚合事件：{len(agg.event_ids)} 条")
        if agg.details:
            details.extend(agg.details[:3])
        return details[:8]

    def finish(self, key: str, reason: str) -> None:
        agg = self.aggregates.get(key)
        if agg is None:
            return
        if agg.kind == "pr" and reason == "failure" and not agg.terminal:
            agg.failure_alerted = True
            agg.flush_at = None
            agg.flush_reason = ""
            return
        self.aggregates.pop(key, None)

    def discard(self, key: str) -> None:
        self.aggregates.pop(key, None)
