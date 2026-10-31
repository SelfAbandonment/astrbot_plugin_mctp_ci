"""MCTP CI 通知卡片：纯逻辑，不依赖 AstrBot，便于单测。"""

from __future__ import annotations

import hashlib
import html
from datetime import datetime
from typing import Any

CARD_WIDTH = 720

STATUS_META = {
    "failure": {"label": "失败", "accent": "#E5484D", "soft": "#FDECEE"},
    "success": {"label": "成功", "accent": "#2F9E44", "soft": "#E9F7EF"},
    "warning": {"label": "警告", "accent": "#D97706", "soft": "#FEF3C7"},
    "fixed": {"label": "已恢复", "accent": "#3E63DD", "soft": "#E8EDFB"},
    "info": {"label": "通知", "accent": "#6B7280", "soft": "#F3F4F6"},
}

EVENT_LABELS = {
    "ci": "CI",
    "pr": "Pull Request",
    "branch": "分支构建",
    "deploy": "生产部署",
    "audit": "依赖巡检",
    "lighthouse": "Lighthouse",
    "contract": "API 契约",
}

RENDER_OPTIONS = {
    "type": "png",
    "full_page": True,
    "scale": "device",
    "omit_background": True,
}

MAX_TITLE = 120
MAX_TEXT = 160
MAX_DETAILS = 8


def _text(value: Any, limit: int = MAX_TEXT) -> str:
    """把任意值收敛成单行字符串并截断。"""
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:limit]


def normalize_payload(data: Any) -> dict[str, Any]:
    """校验并补齐 webhook 字段，避免渲染层拿到奇怪类型。"""
    if not isinstance(data, dict):
        data = {}

    status = _text(data.get("status"), 20).lower() or "info"
    if status not in STATUS_META:
        status = "info"

    event = _text(data.get("event"), 20).lower() or "ci"
    details_raw = data.get("details") or []
    if isinstance(details_raw, str):
        details_raw = [details_raw]
    if not isinstance(details_raw, list):
        details_raw = []
    details = [_text(item, 120) for item in details_raw if _text(item, 120)][:MAX_DETAILS]

    payload = {
        "repo": _text(data.get("repo"), 40) or "MCTP",
        "event": event,
        "event_label": EVENT_LABELS.get(event, event.upper()),
        "status": status,
        "title": _text(data.get("title"), MAX_TITLE) or "CI 通知",
        "subtitle": _text(data.get("subtitle"), MAX_TEXT),
        "branch": _text(data.get("branch"), 80),
        "pr": _text(data.get("pr"), 20),
        "actor": _text(data.get("actor"), 40),
        "commit": _text(data.get("commit"), 12),
        "duration": _text(data.get("duration"), 24),
        "url": _text(data.get("url"), 300),
        "details": details,
        "time": _text(data.get("time"), 40) or datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    payload["id"] = payload_id(payload)
    return payload


def payload_id(payload: dict[str, Any]) -> str:
    """用于短时间去重：同一仓库/事件/标题/链接只发一次。"""
    raw = "|".join(
        str(payload.get(key, "")) for key in ("repo", "event", "status", "title", "url", "commit")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def status_meta(status: str) -> dict[str, str]:
    return STATUS_META.get(status, STATUS_META["info"])


def build_card_html(payload: dict[str, Any]) -> str:
    """生成可直接交给 AstrBot html_render 的 HTML 卡片。"""
    meta = status_meta(payload.get("status", "info"))
    accent = meta["accent"]
    soft = meta["soft"]
    esc = html.escape

    meta_rows: list[str] = []

    def add_row(label: str, value: str) -> None:
        if value:
            meta_rows.append(f'<div class="meta-item"><span>{esc(label)}</span>{esc(value)}</div>')

    if payload.get("pr"):
        add_row("PR", f"#{payload['pr']}")
    if payload.get("branch"):
        add_row("分支", payload["branch"])
    if payload.get("actor"):
        add_row("触发人", payload["actor"])
    if payload.get("commit"):
        add_row("提交", payload["commit"])
    if payload.get("duration"):
        add_row("耗时", payload["duration"])

    details_html = ""
    if payload.get("details"):
        rows = "\n".join(
            f'<div class="detail-row"><span class="dot"></span>{esc(item)}</div>'
            for item in payload["details"]
        )
        details_html = f'<div class="details">{rows}</div>'

    link_html = ""
    if payload.get("url"):
        link_html = f'<div class="link">{esc(payload["url"])}</div>'

    subtitle_html = (
        f'<div class="subtitle">{esc(payload["subtitle"])}</div>' if payload.get("subtitle") else ""
    )

    meta_html = f'<div class="meta">{"".join(meta_rows)}</div>' if meta_rows else ""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: transparent; }}
  body {{
    width: {CARD_WIDTH}px;
    font-family: "Noto Sans CJK SC", "Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif;
    color: #111827;
    padding: 24px;
  }}
  .card {{
    position: relative;
    width: 100%;
    background: #ffffff;
    border-radius: 18px;
    padding: 28px 32px 22px 36px;
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.10);
    overflow: hidden;
  }}
  .bar {{
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 8px;
    background: {accent};
  }}
  .head {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }}
  .repo {{
    font-size: 13px;
    letter-spacing: 0.10em;
    font-weight: 700;
    color: #6b7280;
    text-transform: uppercase;
  }}
  .badge {{
    flex: 0 0 auto;
    padding: 6px 14px;
    border-radius: 999px;
    background: {soft};
    color: {accent};
    font-size: 14px;
    font-weight: 800;
  }}
  h1 {{
    margin: 18px 0 6px;
    font-size: 27px;
    line-height: 1.35;
    letter-spacing: -0.01em;
  }}
  .subtitle {{
    margin-top: 4px;
    font-size: 16px;
    line-height: 1.55;
    color: #6b7280;
  }}
  .meta {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px 20px;
    margin-top: 22px;
  }}
  .meta-item {{
    font-size: 14px;
    color: #374151;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .meta-item span {{
    display: inline-block;
    min-width: 52px;
    margin-right: 8px;
    color: #9ca3af;
    font-size: 13px;
  }}
  .details {{
    margin-top: 20px;
    padding-top: 14px;
    border-top: 1px solid #f1f5f9;
  }}
  .detail-row {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 4px 0;
    font-size: 14px;
    line-height: 1.5;
    color: #374151;
  }}
  .dot {{
    flex: 0 0 auto;
    width: 7px; height: 7px;
    margin-top: 7px;
    border-radius: 50%;
    background: {accent};
    opacity: 0.85;
  }}
  .link {{
    margin-top: 16px;
    padding: 10px 12px;
    border-radius: 10px;
    background: #f8fafc;
    color: #475569;
    font-size: 12px;
    word-break: break-all;
  }}
  .footer {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 20px;
    padding-top: 14px;
    border-top: 1px solid #f1f5f9;
    color: #9ca3af;
    font-size: 12px;
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="bar"></div>
    <div class="head">
      <div class="repo">{esc(payload.get("repo", "MCTP"))}</div>
      <div class="badge">{esc(meta["label"])}</div>
    </div>
    <h1>{esc(payload.get("title", "CI 通知"))}</h1>
    {subtitle_html}
    {meta_html}
    {details_html}
    {link_html}
    <div class="footer">
      <span>MCTP CI · {esc(payload.get("event_label", "CI"))}</span>
      <span>{esc(payload.get("time", ""))}</span>
    </div>
  </div>
</body>
</html>"""


def build_plain_text(payload: dict[str, Any]) -> str:
    """图片渲染失败时的纯文本兜底。"""
    meta = status_meta(payload.get("status", "info"))
    lines = [f"[{meta['label']}] {payload.get('title', 'CI 通知')}"]
    if payload.get("subtitle"):
        lines.append(payload["subtitle"])
    for key, label in (
        ("branch", "分支"),
        ("pr", "PR"),
        ("actor", "触发人"),
        ("duration", "耗时"),
    ):
        if payload.get(key):
            lines.append(f"{label}：{payload[key]}")
    lines.extend(f"- {item}" for item in payload.get("details", []))
    if payload.get("url"):
        lines.append(payload["url"])
    return "\n".join(lines)


def sample_payload() -> dict[str, Any]:
    return normalize_payload(
        {
            "repo": "MCTP-FE",
            "event": "ci",
            "status": "failure",
            "title": "单元测试失败：2 个用例未通过",
            "subtitle": "feat/announcement-pin → develop",
            "pr": "49",
            "branch": "feat/announcement-pin",
            "actor": "MrDai",
            "commit": "8d0df3e",
            "duration": "1m 12s",
            "details": [
                "test: 54 通过 / 2 失败 / 0 跳过",
                "coverage: 71.9% lines（下限 70%）",
                "lint: 通过",
            ],
            "url": "https://github.com/SelfAbandonment/MCTP-Frontend/actions/runs/41180016525",
        }
    )


def test_payload() -> dict[str, Any]:
    """`/ci_test` 用的中性卡片，避免每次测试都显示假的失败数据。"""
    return normalize_payload(
        {
            "repo": "MCTP",
            "event": "ci",
            "status": "success",
            "title": "AstrBot 通知链路正常",
            "subtitle": "这是一条测试卡片，收到即表示 Jenkins → AstrBot 已打通",
            "details": ["触发方式：/ci_test 或 webhook", "图片发送：base64 + 自动裁边"],
        }
    )


def verify_token(provided: str, expected: str) -> bool:
    """常数时间比较，避免时序侧信道。"""
    import hmac

    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)


def merge_targets(configured, stored) -> list[str]:
    """合并配置与 KV 目标，去重并保持顺序。"""
    result: list[str] = []
    for item in list(configured or []) + list(stored or []):
        text = str(item or "").strip()
        if text and ":" in text and text not in result:
            result.append(text)
    return result


def remove_targets(configured, stored, removals) -> tuple[list[str], list[str]]:
    """同时从配置与 KV 中移除目标，返回 (configured, stored)。"""
    blocked = {str(item).strip() for item in removals if str(item).strip()}
    return (
        [item for item in (configured or []) if str(item).strip() not in blocked],
        [item for item in (stored or []) if str(item).strip() not in blocked],
    )


def crop_card(image_path: str, pad: int = 18) -> None:
    """裁掉渲染器固定视口留下的透明/空白边缘。"""
    try:
        from PIL import Image, ImageChops

        image = Image.open(image_path).convert("RGBA")
        bbox = image.getbbox()
        if bbox:
            # 某些渲染器会忽略透明背景，退化为按角落背景色去背
            if bbox[2] - bbox[0] >= image.width - 4 and bbox[3] - bbox[1] >= image.height - 4:
                bg = Image.new("RGBA", image.size, image.getpixel((2, 2)))
                diff = ImageChops.difference(image, bg).convert("L")
                mask = diff.point(lambda value: 255 if value > 5 else 0)
                bbox = mask.getbbox() or bbox
        if not bbox:
            return
        box = (
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(image.width, bbox[2] + pad),
            min(image.height, bbox[3] + pad),
        )
        image.crop(box).save(image_path, "PNG")
    except Exception:  # noqa: BLE001 - 裁切失败就用原图
        pass
