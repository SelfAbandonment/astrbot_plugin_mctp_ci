# Contributing

感谢提交改进。这个仓库是 AstrBot 插件，保持改动小而可验证。

## 流程

1. 从 `main` 拉分支：`feat/<name>`、`fix/<name>`、`docs/<name>`；
2. 改动尽量只涉及插件目录，不要引入 AstrBot 运行时依赖；
3. 提交前运行：

```bash
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

4. PR 描述里写清楚行为变化和验证方式。

## 版本

- `metadata.yaml` 的 `version` 与 `CHANGELOG.md` 同步；
- 行为变化要更新 README 的配置/接口说明；
- 破坏性配置变化需要在 CHANGELOG 标注。

## 安全

- 不要提交 Token、API Key、UMO 或真实群号；
- 示例里用 `<AstrBot地址>`、`abk_xxx` 占位。
