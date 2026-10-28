# 共享课程知识问答

首批使用用户在 2026-10-28 明确选定的 22 篇无待复核标记课程，发布用途为内部参考。
这不等于平台现行规则核验通过。原始草稿不改写，课程正文不提交到代码仓库。

## 结构

- 原生 OpenClaw `memory-core` 和现有本地嵌入模型，独立检索配置及 SQLite 索引。
- 诊断机器人仍使用现有模型，根据检索片段组织回答，不新增模型 API 密钥。
- `hotel-shared-knowledge` 是检索配置的 Agent 名，不新增飞书账号或另一个运行中的网关。
- 原诊断报告、数据库/Excel 选择和人工房型名称流程保持独立。

群内可直接问：

- 酒店动态定价怎么做？
- 浏览多但订单少，应该先排查什么？
- 评价会怎样影响酒店转化率？
- 年度经营目标应该怎么分解？

明确查询本店当天事实、生成报告或执行调价时，不用课程资料代替真实数据和现有业务流程。

## 发布资料

```bash
python scripts/export_shared_knowledge.py --source SOURCE_MARKDOWN_DIR --target NEW_RELEASE_DIR
```

导出器只接受 `knowledge_corpus.APPROVED_COURSES` 中的固定 22 篇，同时要求共享范围和待复核标记为零；缺失、重复或有复核标记时终止。YAML 管理字段不进入导出正文，原始资料不变。导出清单保存正文 SHA-256，运行时重新核对。

每个版本使用新的 release 目录，避免旧索引、撤下课程和新版本混在一起：

```text
/var/lib/hotel-ota-ai/shared-knowledge/
  releases/20261028-r1/
    release.json
    openclaw.json
    workspace/memory/courses/*.md
    state/
    READY.json
    retrieval_tickets.sqlite
  current -> releases/20261028-r1
```

`openclaw.json` 使用一个 `hotel-shared-knowledge` Agent，其 workspace 指向本版本的 `workspace`，`memorySearch.provider=local`，`sources=["memory"]`，不挂 `extraPaths` 或会话。使用已安装模型的 `local.modelPath`；配置不包含飞书账号、酒店数据源或模型 API 密钥。

首次索引命令：

```bash
OPENCLAW_CONFIG_PATH=NEW_RELEASE_DIR/openclaw.json \
OPENCLAW_STATE_DIR=NEW_RELEASE_DIR/state \
openclaw memory status --agent hotel-shared-knowledge --index --json
```

只有返回正常、文件数为 22、无待同步变更、嵌入探测成功且向量维度为 768 后，才写 `READY.json`：

```json
{"version":"2026-10-28-internal-r1","ready":true,"files":22}
```

索引完整后再将 `current` 切向新版本。首建采用本地 CPU，需等待；不要把命令已经启动当作索引已经完成。

## 调用及输出

`skills/hotel-shared-knowledge/SKILL.md` 规定两次调用：

1. `s14_feishu_entry.py --knowledge-context`：先读取 SQLite Active Auth，验证 backend active、可信发送者及当前群的 active 酒店绑定，沿用 S14 现有绑定群只读边界。成功后才能查询课程。返回的 JSON 仅供模型内部使用。
2. `--knowledge-answer DRAFT --knowledge-ticket TICKET`：再次鉴权，校验本群本人的本次检索上下文及正文版本，调用主项目现有 `feishu_output_gate`，自动添加实际检索课程的标题、章节和内部参考说明。最终 stdout 逐字发送一次。

检索上下文有效期 10 分钟，每个群/发送者组合只保留最新一条，不保存原始身份 ID 或用户问题，也不把这些记录加入课程索引。同一上下文不可跨群、跨发送者复用。

检索只接收发布清单中的路径，并按真实文件行号读取原文，不信任工具自带的任意摘要。只要出现额外 Markdown、正文修改、发布状态变化或未就绪索引，就拒绝查询；错误不包含私有路径、异常栈或原始命令。

## 运维配置

- `S14_KNOWLEDGE_ROOT`：默认 `/var/lib/hotel-ota-ai/shared-knowledge/current`，可指定当前已发布版本。
- `S14_OPENCLAW_BIN`：默认 `openclaw`。
- `S14_OUTPUT_GATE_FILE`：默认 `/opt/openclaw/workspaces/hotel-ota-ai/runtime/safety/feishu_output.py`，必须是受控主项目中的现有输出闸门；不存在或调用失败时拒绝输出。
- SQLite 继续使用既有 `HOTEL_OTA_DB`，不新增角色、群绑定或全局管理员。

当前入口只支持已有绑定的诊断群，与现有 S14 群读取范围一致。没有增加私聊酒店选择或跨酒店管理能力。

新增或撤下课程要明确更新发布范围、生成新版本、完成全量索引再切换；仅修改 Markdown 的草稿状态不会自动成为发布或撤下操作。
