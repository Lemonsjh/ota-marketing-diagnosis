# S14 经营诊断报告契约

诊断由独立项目的 `operation-diagnosis` Agent 提供。主机器人识别到酒店经营诊断请求时，引导用户在群内询问诊断机器人。

## 请求

飞书诊断流程先选择数据来源，用户可回复“数据库”或“上传Excel”。Excel 选择后等待同一用户在同一群上传文件。酒店范围来自可信机器人账号与会话鉴权，渠道范围以酒店配置为准。

Skill 输入使用 `hotel_id` 和 `data_source_mode`。报告数据源模式为 `database` 或 `excel_upload`，后者需要 `input_excel_path`。内部固定请求 `platform=multi`，实际分析和展示遵循酒店启用渠道。支持 `period_start`、`period_end`、`period_days` 及房型名称等可选输入。

## 结果与产物

成功生成后返回 `skill_id`、`run_id`、酒店和周期、评分与诊断数据、`report_url`、`report_file_path`、`report_json`、`report_markdown`、`feishu_message`、`feishu_card`，以及 `approval_required=false`、`dry_run=true`。

报告写入 `S14_REPORT_OUTPUT_DIR/<hotel_id>/multi/<start>_<end>/<run_id>/`，包含 HTML、JSON 和 Markdown。配置 `S14_PUBLIC_BASE_URL` 时，公开报告地址由该前缀和报告相对路径组成。未配置时 Skill 可能返回本地文件 URI，不能将它当作可供飞书用户访问的公开链接。

普通飞书回复使用运行时的 `feishu_message`，只有真实生成且可访问的报告地址才能作为报告链接。结构化适配器可使用 `feishu_card`；CLI 文本流程不输出卡片 JSON、服务器路径或完整内部结果。报告不触发审批、价格、库存、推广或评论写入。

## 事实源

输入、来源选择和输出字段以 `skills/s14-operation-diagnosis/openclaw.skill.yaml` 及其 runtime 为准。展示结构与评分以 `marketing_diagnosis/` 的当前实现及测试为准。
