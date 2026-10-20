# 个人模型配置帮助：官方资料核对

核验日期：2026-10-18。仅查公开官方文档，没有使用真实 Key、充值或调用模型。OpenAI 部分使用 [OpenAI Docs 技能](C:/Users/19687/.codex/skills/.system/openai-docs/SKILL.md) 查阅官方资料。

| 供应商 | 正式帮助入口与本轮核对结论 |
| --- | --- |
| OpenAI | [快速入门](https://developers.openai.com/api/docs/quickstart)、[模型目录](https://developers.openai.com/api/docs/models)、[价格](https://developers.openai.com/api/docs/pricing)。创建本人 API Key、核对模型支持的接口及本人权限。官方存在按量计价；不把网页订阅或一次测试待遇解释为所有 API 永久免费。 |
| DeepSeek | [模型及价格](https://api-docs.deepseek.com/quick_start/pricing/)、[首个调用](https://api-docs.deepseek.com/)。官方列出模型、JSON 能力、按 token 扣费和余额扣减；赠送余额与充值余额不同。不将网页免费聊天等同免费 API，不固化旧模型别名。 |
| SiliconFlow | [快速入门](https://docs.siliconflow.cn/docs/userguide/quickstart)、[免费模型和限流说明](https://docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation)、[模型广场](https://cloud.siliconflow.cn/models)。官方说明实名后免费模型调用费用为0且限流固定；可把本人模型广场当前标识免费的模型作为候选。未登录核验具体免费模型 ID，不指定默认，不保证永久免费或业务 JSON 质量。 |

操作：选择供应商 → 官方控制台创建本人 Key → 复制准确聊天模型 ID → 保存本组 → 主动测试已保存版本 → 查看通过／失败和修复提示 → 逐篇主动分析。保存不联网；测试只是连通证据。奖励判定与定价走判定用途，整理／回顾用辅助用途；实际来源记录在建议中。

“其他兼容接口”仅接受公网 HTTPS 443，禁止 URL 中凭据／查询参数、回环／内网／元数据 IP。出站时重新解析 DNS、拒绝任何非公网地址、固定已验证 IP、保持原 Host 和 TLS 校验，并关闭重定向与环境代理。更换自定义主机须重绑 Key，不能把旧凭据发给新主机。隔离测试不代替供应商实际连通验收。
