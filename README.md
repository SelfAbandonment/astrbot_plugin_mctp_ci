# MCTP Beacon

> `astrbot_plugin_mctp_ci` · CI 结果像信号一样，以卡片形式发到群里。

[![CI](https://github.com/SelfAbandonment/astrbot_plugin_mctp_ci/actions/workflows/ci.yml/badge.svg)](https://github.com/SelfAbandonment/astrbot_plugin_mctp_ci/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.9.2-6f42c1.svg)](https://astrbot.app)

MCTP CI/CD 的 AstrBot 通知插件：CI 推送一条 JSON，插件用 AstrBot 自带的
`html_render`（HTML + Chromium）渲染成 PNG 卡片，再主动发到群里。

> 产品名叫 **MCTP Beacon（信标）**；插件 ID 保持 `astrbot_plugin_mctp_ci`，避免已安装实例重装和重新绑定。

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
   - `targets`：留空，之后在目标群发 `/ci_bind`；也可 `/ci_bind <群号>` 直接绑定
   - `author_mentions`：可选，每项格式 `GitHub登录名=QQ号[,QQ号]`，例如 `MrDai=123456,234567`
   - `mention_on`：哪些状态/事件 @ 作者，默认 `failure`、`approved`、`comment`
   - `author_targets`：按 PR 作者路由群，格式 `登录名=群号[,群号]`，例如 `MrDai=123456`
   - `repo_targets`：按仓库路由群，格式 `REPO=群号[,群号]`，例如 `MCTP-FE=123456`
   - `at_all_on_failure`：未配置作者映射时，失败是否 @全体，默认关
4. 在目标群发 `/ci_test`，应收到一张“链路正常”的测试卡片。

> 只声明 `Pillow`（见 `requirements.txt`）；`aiohttp` 由 AstrBot 核心提供，不要重复声明，否则会和核心版本约束冲突。

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

同一 `repo+event+status+title+url+commit` 在 2 分钟内对每个目标最多成功发送一次，避免 Jenkins 重试刷屏；失败目标会在重试时单独补发，没有绑定会话时不会消耗去重窗口。构建链接只放在卡片内部，不再额外发送图片下方的链接文本。
`author_mentions` 匹配 `actor` 时，会按 `mention_on` 决定是否 @：默认失败、PR 通过、PR 评论都 @；映射可一对多、登录名不区分大小写。未配置映射时不 @任何人；`at_all_on_failure` 只在完全未配置 `author_mentions` 时生效。
路由优先级：`author_targets`（按 PR 作者）> `repo_targets`（按仓库）> 全局 `targets`。未配置作者/仓库路由时行为跟以前一致。
生产部署生命周期应由实际运行部署的 Jenkins job 在 start/success/failure/rollback 时调用通知入口，设置 `event: "deploy"`、`status`、`actor`、`url` 和当前结果明细。release workflow 收到 Jenkins 的 HTTP 接收响应不能当作部署成功；回滚状态需由 Jenkins 部署逻辑显式报告。

## 指令

| 指令 | 作用 |
|---|---|
| `/ci_bind` | 把当前群绑定为通知接收方 |
| `/ci_bind <群号>` | 直接按 QQ 群号绑定（群号见 `/ci_groups`） |
| `/ci_groups` | 查看机器人已加入的 QQ 群和群号 |
| `/ci_unbind` | 解除当前会话绑定 |
| `/ci_unbind <序号>` | 解除指定会话（序号见 `/ci_targets`） |
| `/ci_unbind all` | 清空全部绑定 |
| `/ci_targets` | 查看已绑定会话、序号和来源 |
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
- health 响应中的 `delivery_ok` / `last_error`：查看最近一次通知是否完整送达；`ok` 只表示健康接口可用；
- 401：`X-CI-Token` 与插件配置不一致（dashboard 还要检查 API Key 是否有效）；
- 403：API Key 没有 `plugin` scope；
- 409：还没有绑定会话，先在目标群发 `/ci_bind`；
- 503：`webhook_token` 没配置；
- 卡片没图：检查 AstrBot 的 t2i/Chromium 是否正常，插件会自动回退纯文本。
- `at_all_on_failure` 在图片发送和纯文本回退两种路径都会生效。
- `author_mentions` 使用 GitHub login 到 QQ 用户 ID 的映射；`MCTP-Notify` 需要把 `ACTOR` 参数转发为 webhook JSON 的 `actor` 字段。

## 开发与测试

```bash
pip install -r requirements.txt ruff
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

发布新版本时同步更新 `metadata.yaml` 的 `version` 和 `CHANGELOG.md`。
