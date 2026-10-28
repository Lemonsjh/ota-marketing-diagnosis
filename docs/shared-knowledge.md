# 共享课程知识问答

用户已于 2026-10-28 明确要求全部投入使用，当前资料中的 42 篇共享课程均纳入清单，作为内部参考。多个酒店共用一份资料，现有诊断机器人负责回答；不新增飞书账号、网关或模型密钥。

## 固定目录

```text
/var/lib/hotel-ota-ai/shared-knowledge/
  memory/          # 课程正文，每篇一个 Markdown
  courses.json     # 允许检索的课程编号清单
  openclaw.json    # 原生 memory 检索配置
  state/           # 原生索引和临时问答上下文
```

没有版本目录、当前版本软链接或就绪标记文件。`courses.json` 只是课程编号数组；例如编号 `OP-008` 对应 `memory/OP-008.md`，标题从正文首行 `# 标题` 读取。

`openclaw.json` 中的 `hotel-shared-knowledge` 使用上述固定目录作为 workspace，`memorySearch.provider=local`、`sources=["memory"]`，并指定现有本地模型的 `local.modelPath`。课程正文与酒店会话、经营报告及主机器人记忆分开。

## 更新资料

修改现有课程时，直接编辑 `memory/` 下的 Markdown，再更新原生索引：

```bash
OPENCLAW_CONFIG_PATH=/var/lib/hotel-ota-ai/shared-knowledge/openclaw.json \
OPENCLAW_STATE_DIR=/var/lib/hotel-ota-ai/shared-knowledge/state \
openclaw memory status --agent hotel-shared-knowledge --index --json
```

新增或撤下课程时，同时调整 `memory/` 中的文件和 `courses.json` 清单，再运行上述命令。增加已批准课程不需要修改程序或创建新版本。管理记录、酒店数据和 YAML 管理字段不放进正文。

原始整理资料可用 `scripts/export_shared_knowledge.py --source 原始目录 --target 上述固定目录` 转成纯正文。工具导出输入目录中所有 `scope=shared` 的课程，不再按待复核标记筛掉整篇；管理字段不进入正文。之后直接维护正文和清单即可。

程序根据原生 SQLite 索引中的文件及内容摘要，确认索引与当前正文一致，不再另外维护就绪标记。资料改动后尚未更新索引时，查询会提示暂不可用；已有向量缓存会在更新索引时复用。

## 问答入口

在已绑定酒店的诊断群中直接问“酒店动态定价怎么做”“浏览多但订单少怎么排查”等通用方法。知识问答不要求选择数据库或上传 Excel；实际经营报告仍走原有诊断流程。

`hotel-shared-knowledge` Skill 先通过 `s14_feishu_entry.py --knowledge-context` 检查 SQLite 绑定群权限并检索课程，再由现有模型组织答案，最后用 `--knowledge-answer` 检查输出并添加课程标题、章节和内部参考说明。检索 JSON 只供模型内部使用。

同群、同发送者的检索上下文有效期 10 分钟，保存在 `state/qa.sqlite`；每个群/发送者组合只保留最新一条。最终回复仍经过主项目现有的 Feishu 输出闸门，知识问答不执行调价或其他业务写入。

## 配置项

- `S14_KNOWLEDGE_ROOT`：默认 `/var/lib/hotel-ota-ai/shared-knowledge`。
- `S14_OPENCLAW_BIN`：默认 `openclaw`。
- `S14_OUTPUT_GATE_FILE`：默认 `/opt/openclaw/workspaces/hotel-ota-ai/runtime/safety/feishu_output.py`。
- SQLite 继续使用既有 `HOTEL_OTA_DB`；未改变角色、群绑定或现有模型配置。
