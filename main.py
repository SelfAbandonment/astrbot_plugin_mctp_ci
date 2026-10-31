"""AstrBot 插件：MCTP CI/CD 美观通知卡片。

支持两种接入方式：
1. standalone：插件自己监听一个端口（默认 6199），适合能映射端口的环境；
2. dashboard：复用 AstrBot 的 6185 端口，通过插件 Web API 接收（需要 API Key 的 plugin scope）。

CI 推送 JSON 后，插件用 AstrBot 的 html_render 渲染成 PNG 卡片，再主动发送到已绑定会话。
"""

from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Any

from aiohttp import web
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register
from astrbot.api.web import json_response
from astrbot.api.web import request as web_request

try:  # 兼容 AstrBot 以包/单文件两种方式加载插件
    from .core import (
        RENDER_OPTIONS,
        build_card_html,
        build_plain_text,
        crop_card,
        merge_targets,
        normalize_payload,
        remove_targets,
        test_payload,
        verify_token,
    )
except ImportError:  # pragma: no cover - 单文件加载时的兜底
    from core import (
        RENDER_OPTIONS,
        build_card_html,
        build_plain_text,
        crop_card,
        merge_targets,
        normalize_payload,
        remove_targets,
        test_payload,
        verify_token,
    )

logger = logging.getLogger("astrbot")

PLUGIN_NAME = "astrbot_plugin_mctp_ci"
DEDUP_TTL = 120
DEDUP_MAX = 100


@register(
    PLUGIN_NAME,
    "SelfAbandonment",
    "MCTP Beacon · CI/CD 美观通知卡片（Jenkins / GitHub Actions）",
    "0.2.8",
)
class MctpCiNotifier(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._runner: web.AppRunner | None = None
        self._seen: dict[str, float] = {}
        self._last_error: str = ""
        self._mode = "standalone"

    # ------------------------------------------------------------------ 生命周期
    async def initialize(self) -> None:
        raw_mode = str(self.config.get("mode") or "standalone").strip().lower()
        if raw_mode not in {"standalone", "dashboard"}:
            logger.warning("[MCTP-CI] 未知 mode=%s，回退 standalone", raw_mode)
            raw_mode = "standalone"
        self._mode = raw_mode

        if not str(self.config.get("webhook_token") or ""):
            logger.warning("[MCTP-CI] webhook_token 未配置，webhook 会返回 503")

        if self._mode == "dashboard":
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/webhook",
                self._handle_dashboard_webhook,
                ["POST"],
                "MCTP CI webhook",
            )
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/health",
                self._handle_dashboard_health,
                ["GET"],
                "MCTP CI health",
            )
            logger.info(
                "[MCTP-CI] dashboard 模式：POST /api/v1/plugins/extensions/%s/webhook",
                PLUGIN_NAME,
            )
            return

        host = str(self.config.get("listen_host") or "0.0.0.0")
        try:
            port = int(self.config.get("listen_port") or 6199)
        except (TypeError, ValueError):
            port = 6199
        if not 1 <= port <= 65535:
            logger.warning("[MCTP-CI] listen_port=%s 非法，回退 6199", port)
            port = 6199

        app = web.Application(client_max_size=64 * 1024)
        app.router.add_get("/health", self._handle_standalone_health)
        app.router.add_post("/mctp-ci", self._handle_standalone_webhook)

        runner = web.AppRunner(app, access_log=None)
        try:
            await runner.setup()
            site = web.TCPSite(runner, host, port)
            await site.start()
        except OSError as exc:
            self._last_error = f"监听 {host}:{port} 失败：{exc}"
            logger.error(
                "[MCTP-CI] %s；如果只能使用 6185，请把插件模式改为 dashboard", self._last_error
            )
            await runner.cleanup()
            return

        self._runner = runner
        logger.info("[MCTP-CI] standalone webhook 已启动：http://%s:%s/mctp-ci", host, port)

    async def terminate(self) -> None:
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            finally:
                self._runner = None
        logger.info("[MCTP-CI] webhook 已停止")

    # ------------------------------------------------------------------ 目标会话
    def _configured_targets(self) -> list[str]:
        configured = self.config.get("targets") or []
        if isinstance(configured, str):
            configured = [configured]
        return [str(item or "").strip() for item in configured if str(item or "").strip()]

    async def _stored_targets(self) -> list[str]:
        stored = await self.get_kv_data("targets", [])
        if not isinstance(stored, list):
            return []
        return [str(item or "").strip() for item in stored if str(item or "").strip()]

    async def _targets(self) -> list[str]:
        return merge_targets(self._configured_targets(), await self._stored_targets())

    async def _store_targets(self, targets: list[str]) -> None:
        await self.put_kv_data("targets", targets)

    def _save_configured_targets(self, targets: list[str]) -> None:
        self.config["targets"] = targets
        save = getattr(self.config, "save_config", None)
        if callable(save):
            save()

    async def _remove_targets(self, removals: list[str]) -> None:
        configured, stored = remove_targets(
            self._configured_targets(), await self._stored_targets(), removals
        )
        await self._store_targets(stored)
        self._save_configured_targets(configured)

    # ------------------------------------------------------------------ 公共处理
    async def _dispatch(self, provided_token: str, data: Any) -> tuple[int, dict[str, Any]]:
        expected = str(self.config.get("webhook_token") or "")
        if not expected:
            return 503, {"ok": False, "error": "webhook_token 未配置"}
        if not verify_token(provided_token, expected):
            return 401, {"ok": False, "error": "invalid token"}

        payload = normalize_payload(data)
        logger.info(
            "[MCTP-CI] 收到通知 repo=%s event=%s status=%s",
            payload["repo"],
            payload["event"],
            payload["status"],
        )
        if payload["id"] in self._seen and time.time() - self._seen[payload["id"]] < DEDUP_TTL:
            return 200, {"ok": True, "skipped": "duplicate"}
        self._seen[payload["id"]] = time.time()
        self._prune_seen()

        targets = await self._targets()
        if not targets:
            return 409, {"ok": False, "error": "没有目标会话，先在群里发 /ci_bind"}

        sent = await self._send_payload(payload, targets)
        if sent == 0:
            return 502, {"ok": False, "error": "所有目标发送失败，查看 AstrBot 日志"}
        return 200, {"ok": True, "sent": sent, "event": payload["event"]}

    async def _send_payload(self, payload: dict[str, Any], targets: list[str]) -> int:
        image_data = ""
        try:
            image_path = await self.html_render(
                build_card_html(payload),
                {},
                return_url=False,
                options=RENDER_OPTIONS,
            )
            image_data = self._image_data(image_path)
        except Exception as exc:  # noqa: BLE001 - 渲染失败要兜底成文本
            logger.exception("[MCTP-CI] 渲染卡片失败，回退纯文本")
            self._last_error = f"render: {exc}"

        text_fallback = build_plain_text(payload)
        at_all = payload["status"] == "failure" and bool(
            self.config.get("at_all_on_failure", False)
        )

        sent = 0
        for umo in targets:
            if image_data:
                chain = MessageChain().base64_image(image_data)
                if at_all:
                    chain.at_all()
                try:
                    await self.context.send_message(umo, chain)
                    sent += 1
                    continue
                except Exception as exc:  # noqa: BLE001 - 图片发送失败时回退纯文本
                    logger.warning("[MCTP-CI] 发送图片到 %s 失败：%s", umo, exc)
            try:
                await self.context.send_message(umo, MessageChain().message(text_fallback))
                sent += 1
                logger.info("[MCTP-CI] 已用纯文本回退发送到 %s", umo)
            except Exception as exc:  # noqa: BLE001 - 单个会话失败不影响其他会话
                logger.warning("[MCTP-CI] 文本回退也失败 %s：%s", umo, exc)
        return sent

    @staticmethod
    def _image_data(image_path: str) -> str:
        """裁边并转成 base64，避免 NapCat 读不到 AstrBot 容器内的本地路径。"""
        crop_card(image_path)
        return base64.b64encode(Path(image_path).read_bytes()).decode("ascii")

    def _prune_seen(self) -> None:
        if len(self._seen) <= DEDUP_MAX:
            return
        cutoff = time.time() - DEDUP_TTL
        self._seen = {key: ts for key, ts in self._seen.items() if ts >= cutoff}

    async def _health_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "plugin": PLUGIN_NAME,
            "mode": self._mode,
            "targets": len(await self._targets()),
            "last_error": self._last_error,
        }

    # ------------------------------------------------------------------ dashboard 模式
    async def _handle_dashboard_webhook(self):
        data = await web_request.json(default={})
        status, body = await self._dispatch(web_request.headers.get("X-CI-Token", ""), data)
        return json_response(body, status_code=status)

    async def _handle_dashboard_health(self):
        return json_response(await self._health_payload())

    # ------------------------------------------------------------------ standalone 模式
    async def _handle_standalone_health(self, request: web.Request) -> web.Response:
        return web.json_response(await self._health_payload())

    async def _handle_standalone_webhook(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)
        status, body = await self._dispatch(request.headers.get("X-CI-Token", ""), data)
        return web.json_response(body, status=status)

    # ------------------------------------------------------------------ 指令
    @staticmethod
    def _command_arg(event: AstrMessageEvent) -> str:
        raw = str(getattr(event, "message_str", "") or "").strip()
        parts = raw.split()
        if len(parts) > 1:
            return parts[1].strip()
        return raw if raw.isdigit() or raw.lower() == "all" else ""

    @filter.command("ci_help")
    async def ci_help(self, event: AstrMessageEvent):
        """查看 CI 通知指令说明。"""
        yield event.plain_result(
            "CI 通知指令：\n"
            "/ci_bind 绑定当前会话\n"
            "/ci_unbind 解除当前会话\n"
            "/ci_unbind <序号> 解除指定会话（序号见 /ci_targets）\n"
            "/ci_unbind all 清空全部绑定\n"
            "/ci_targets 查看已绑定会话\n"
            "/ci_test 发一张测试卡片"
        )

    @filter.command("ci_bind")
    async def ci_bind(self, event: AstrMessageEvent):
        """把当前会话绑定为 CI 通知接收方。"""
        umo = event.unified_msg_origin
        targets = await self._targets()
        if umo in targets:
            yield event.plain_result("这个会话已经绑定过了。")
            return
        stored = await self._stored_targets()
        stored.append(umo)
        await self._store_targets(stored)
        yield event.plain_result(f"已绑定 CI 通知（共 {len(targets) + 1} 个会话）。")

    @filter.command("ci_unbind")
    async def ci_unbind(self, event: AstrMessageEvent):
        """解除绑定：默认当前会话，支持序号或 all。"""
        targets = await self._targets()
        if not targets:
            yield event.plain_result("还没有绑定任何会话。")
            return

        arg = self._command_arg(event)
        if arg.lower() == "all":
            removals = targets
            label = "全部会话"
        elif arg.isdigit():
            index = int(arg)
            if not 1 <= index <= len(targets):
                yield event.plain_result(f"序号超出范围：1-{len(targets)}")
                return
            removals = [targets[index - 1]]
            label = f"第 {index} 个会话"
        elif arg:
            yield event.plain_result("用法：/ci_unbind、/ci_unbind 2、/ci_unbind all")
            return
        else:
            removals = [event.unified_msg_origin]
            label = "当前会话"

        existing = [item for item in removals if item in targets]
        if not existing:
            yield event.plain_result("要解除的会话不在绑定列表里。")
            return

        await self._remove_targets(existing)
        remaining = await self._targets()
        yield event.plain_result(f"已解除 {label} 的绑定（剩余 {len(remaining)} 个会话）。")

    @filter.command("ci_targets")
    async def ci_targets(self, event: AstrMessageEvent):
        """查看已绑定的会话与来源。"""
        targets = await self._targets()
        if not targets:
            yield event.plain_result("还没有绑定任何会话，先发 /ci_bind。")
            return
        configured = set(self._configured_targets())
        stored = set(await self._stored_targets())
        lines = []
        for idx, item in enumerate(targets, start=1):
            if item in configured and item in stored:
                source = "配置+会话"
            elif item in configured:
                source = "配置"
            else:
                source = "会话"
            lines.append(f"{idx}. {item}（{source}）")
        yield event.plain_result("已绑定会话：\n" + "\n".join(lines))

    @filter.command("ci_test")
    async def ci_test(self, event: AstrMessageEvent):
        """发一张示例卡片，检查渲染和图片发送是否正常。"""
        payload = test_payload()
        try:
            image_path = await self.html_render(
                build_card_html(payload),
                {},
                return_url=False,
                options=RENDER_OPTIONS,
            )
            yield event.chain_result(
                MessageChain().base64_image(self._image_data(image_path)).chain
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[MCTP-CI] 示例卡片渲染失败")
            self._last_error = f"render: {exc}"
            yield event.plain_result("示例卡片渲染失败，已回退文本：\n" + build_plain_text(payload))
