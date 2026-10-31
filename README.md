# astrbot_plugin_mctp_ci

[![CI](https://github.com/SelfAbandonment/astrbot_plugin_mctp_ci/actions/workflows/ci.yml/badge.svg)](https://github.com/SelfAbandonment/astrbot_plugin_mctp_ci/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.9.2-6f42c1.svg)](https://astrbot.app)

MCTP CI/CD 的 AstrBot 通知插件：CI 推送一条 JSON，插件用 AstrBot 自带的
`html_render`（HTML + Chromium）渲染成 PNG 卡片，再主动发到群里。

比直连 AstrBot HTTP API 多出来的能力：

- **图片卡片**：状态色、仓库、标题、分支/PR/触发人/耗时、明细、链接，一条消息看完
- **base64 发图**：NapCat/协议端读不到 AstrBot 容器内的临时文件，插件默认用 base64 图片段发送
- **自动裁边**：渲染器固定视口会留大片空白，插件用 Pillow 按透明边/背景色裁成紧凑卡片
- **订阅制**：在群里发 `/ci_bind` 就绑定，不用在 CI 里硬编码 UMO
- **两种接入模式**：
  - `standalone`：插件自己监听一个端口，CI 只带 `X-CI-Token`，不需要 AstrBot API Key
  - `dashboard`：复用 AstrBot 的 **6185** 端口，适合只能开 6185、不能加端口映射的环境

## 两种模式怎么选

| | standalone | dashboard |
|---|---|---|
| 端口 | 插件另开一个端口（默认 6199），需要 Docker `-p 6199:6199` + 安全组 | 只用 AstrBot 的 6185，不需要新端口 |
| CI 鉴权 | 只带 `X-CI-Token` | `Authorization: Bearer abk_...`（`plugin` scope）+ `X-CI-Token` |
| 安全面 | 插件只暴露一个通知入口 | API Key 带 `plugin` scope，能管理插件，建议专用 + 定期轮换 |
| 适用 | 能自由开端口 | **只能开 6185（当前情况）** |

> 如果你的 Docker 端口只有 `6185->6185`，**选 dashboard**。

## 安装

### 从 GitHub 安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/SelfAbandonment/astrbot_plugin_mctp_ci.git
```

然后在 AstrBot WebUI 插件页重载/启用。

### 手动安装

1. 把整个 `astrbot_plugin_mctp_ci/` 目录放到 AstrBot 的 `data/plugins/` 下；
2. 在 WebUI 插件页重载/启用；
3. 在插件配置里填：
   - `mode`：`dashboard`（只能开 6185）或 `standalone`（能开 6199）
   - `webhook_token`：随机长串，例如 `openssl rand -hex 24`
   - `listen_host` / `listen_port`：standalone 才用；dashboard 忽略，保持默认即可
   - `targets`：留空，之后在目标群发 `/ci_bind`
   - `at_all_on_failure`：失败是否 @全体，默认关
4. 在目标群发 `/ci_test`，应收到一张“链路正常”的测试卡片。

> 依赖 `Pillow` 和 `aiohttp`（见 `requirements.txt`），AstrBot 镜像通常已自带；缺失时在 AstrBot 环境安装。

## dashboard 模式（只能开 6185）

### 1. 创建 API Key

AstrBot WebUI → 设置 → OpenAPI → 新建 API Key，scope 勾选 **`plugin`**。
这个 scope 同时允许管理插件，所以：

- 只给 Jenkins 用，别泄露；
- 定期轮换；
- 如果以后能开 6199，切换到 standalone 可以完全不用这个 Key。

### 2. CI 调用

```bash
curl -fsS -X POST "http://<AstrBot地址>:6185/api/v1/plugins/extensions/astrbot_plugin_mctp_ci/webhook" \
  -H "Authorization: Bearer $ASTRBOT_API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-CI-Token: $ASTRBOT_WEBHOOK_TOKEN" \
  -d '{
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
    "details": ["test: 54 通过 / 2 失败", "coverage: 71.9% lines"],
    "url": "https://github.com/.../actions/runs/123"
  }'
```

健康检查：

```bash
curl -fsS "http://<AstrBot地址>:6185/api/v1/plugins/extensions/astrbot_plugin_mctp_ci/health" \
  -H "Authorization: Bearer $ASTRBOT_API_KEY"
```

## standalone 模式（能开 6199）

```bash
# Docker 增加端口映射
-p 6199:6199

curl -fsS -X POST "http://<AstrBot地址>:6199/mctp-ci" \
  -H "Content-Type: application/json" \
  -H "X-CI-Token: $ASTRBOT_WEBHOOK_TOKEN" \
  -d '{"repo":"MCTP-FE","event":"ci","status":"failure","title":"构建失败"}'
```

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `repo` | 否 | 仓库名，默认 `MCTP` |
| `event` | 否 | `ci`/`pr`/`branch`/`deploy`/`audit`/`lighthouse`/`contract` |
| `status` | 否 | `failure`/`success`/`warning`/`fixed`/`info`，决定卡片颜色 |
| `title` | 是 | 主标题，建议一句话说清失败点 |
| `subtitle` | 否 | 分支流向、补充说明 |
| `pr`/`branch`/`actor`/`commit`/`duration` | 否 | 元信息，有值才显示 |
| `details` | 否 | 字符串数组，最多 8 条 |
| `url` | 否 | 构建/PR/部署链接 |

同一 `repo+event+status+title+url+commit` 在 2 分钟内只发一次，避免 Jenkins 重试刷屏。

## 指令

| 指令 | 作用 |
|---|---|
| `/ci_bind` | 把当前会话绑定为通知接收方 |
| `/ci_unbind` | 解除当前会话绑定 |
| `/ci_targets` | 查看已绑定会话 |
| `/ci_test` | 发一张中性的“链路正常”测试卡片（不再显示假的失败数据） |

## Jenkins 接入示例

```groovy
post {
    failure {
        withCredentials([
            string(credentialsId: 'astrbot-api-key', variable: 'ASTRBOT_API_KEY'),
            string(credentialsId: 'astrbot-webhook-token', variable: 'ASTRBOT_WEBHOOK_TOKEN')
        ]) {
            sh '''
              curl -fsS -X POST "$ASTRBOT_URL/api/v1/plugins/extensions/astrbot_plugin_mctp_ci/webhook" \
                -H "Authorization: Bearer $ASTRBOT_API_KEY" \
                -H "Content-Type: application/json" \
                -H "X-CI-Token: $ASTRBOT_WEBHOOK_TOKEN" \
                -d "{\\"repo\\":\\"MCTP-FE\\",\\"event\\":\\"ci\\",\\"status\\":\\"failure\\",\\"title\\":\\"构建失败\\",\\"branch\\":\\"${BRANCH_NAME}\\",\\"url\\":\\"${BUILD_URL}\\"}" \
                || echo "AstrBot 通知失败（不影响构建）"
            '''
        }
    }
}
```

`ASTRBOT_URL` 建议放在 Jenkins 全局环境变量里，例如 `http://1.2.3.4:6185`。

## 安全

- 必须设置 `webhook_token`；为空时 webhook 直接返回 503。
- standalone 建议只在内网/安全组白名单暴露端口；dashboard 依赖 6185 的 HTTPS/反代。
- dashboard 模式的 API Key 带 `plugin` scope，权限较大，务必专用和轮换。
- 插件不打印 Token/Authorization；`at_all_on_failure` 默认关闭。

## 排错

- health 返回 200：端口/路由正常；
- 401：`X-CI-Token` 与插件配置不一致（dashboard 还要检查 API Key 是否有效）；
- 403：API Key 没有 `plugin` scope；
- 409：还没有绑定会话，先在目标群发 `/ci_bind`；
- 503：`webhook_token` 没配置；
- 卡片没图：检查 AstrBot 的 t2i/Chromium 是否正常，插件会自动回退纯文本。

## 开发与测试

```bash
pip install -r requirements.txt ruff
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

发布新版本时同步更新 `metadata.yaml` 的 `version` 和 `CHANGELOG.md`。
