# Changelog

## 0.2.4 - 2026-10-31

### Changed

- 产品命名 **MCTP Beacon（MCTP 信标）**
- 插件 ID 保持 `astrbot_plugin_mctp_ci`，已安装实例无需重装

## 0.2.3 - 2026-10-31

### Added

- Jenkins 失败 / 恢复 / Lighthouse 警告通知的实际接入验证
- Pillow 自动裁边：裁掉 AstrBot 渲染器固定视口留下的透明空白
- `/ci_test` 改为中性的“通知链路正常”卡片

### Fixed

- QQ/NapCat 发送本地图片报 `rich media transfer failed`：改用 base64 图片段
- 图片发送失败时自动回退纯文本
- Jenkins 通知耗时显示“并计数中”：改为实际已耗时
- 任务名中的 `%2F` 解码为 `/`

## 0.2.2 - 2026-10-31

### Added

- 自动裁边
- 实际耗时

## 0.2.1 - 2026-10-31

### Fixed

- 使用 base64 发送图片，兼容 NapCat/协议端读不到容器文件的问题
- 发送失败自动回退纯文本

## 0.2.0 - 2026-10-31

### Added

- `dashboard` 模式：复用 AstrBot 6185 端口的插件 Web API
- `/ci_bind`、`/ci_unbind`、`/ci_targets`、`/ci_test`
- 图片卡片、去重、失败 @全体

## 0.1.0 - 2026-10-31

### Added

- 初始版本：独立端口 webhook + 文本/图片通知
