# 首版范围与待决事项

状态：产品边界按 JT 确认；具体技术与数值仍按 ADR/Issue 验证。用户旅程为“提出需求 → 查询有来源的信息 → 审阅草稿 → 接受为正式旅程 → 手动或助手局部修改 → 重开继续使用”，并由完整长记忆减少重复解释。

## 首版必须交付

| 能力 | 行为与任务归属 |
|---|---|
| 账号与隔离 | 新用户建号、受邀准入、登录/退出/恢复/注销；两个真实账号验证隔离。CJ-007 [#8](https://github.com/JTCAO515/Go2China/issues/8)、CJ-024 [#27](https://github.com/JTCAO515/Go2China/issues/27) |
| 对话与恢复 | 历史、持久接收、JSON/SSE 候选传输、停止、原结果查询、单一终态、同聊天顺序；调用前限额。CJ-008/009/010 [#9](https://github.com/JTCAO515/Go2China/issues/9)、[#10](https://github.com/JTCAO515/Go2China/issues/10)、[#11](https://github.com/JTCAO515/Go2China/issues/11) |
| 真实旅行规划 | 需求纠正、地点/路线、时效来源、可行/不可行/未知、可审阅草稿；未知日期/预算允许探索，不伪装精确验证。CJ-012/013/014/034/035 [#13](https://github.com/JTCAO515/Go2China/issues/13)、[#14](https://github.com/JTCAO515/Go2China/issues/14)、[#19](https://github.com/JTCAO515/Go2China/issues/19)、[#16](https://github.com/JTCAO515/Go2China/issues/16)、[#18](https://github.com/JTCAO515/Go2China/issues/18) |
| 正式旅程 | 接受/拒绝、版本与动作回执、每日时间线/地图/现场中英地点、手动编辑、固定事项保护、选定范围的助手修改。CJ-015～018 [#20](https://github.com/JTCAO515/Go2China/issues/20)、[#21](https://github.com/JTCAO515/Go2China/issues/21)、[#22](https://github.com/JTCAO515/Go2China/issues/22)、[#25](https://github.com/JTCAO515/Go2China/issues/25) |
| 完整长记忆 | 静态事实、经历、偏好；及时增量、会话结束摘要、归纳确认、跨旅行检索、条目编辑/启停/删除、防复活。CJ-011/019/020/021，见[规格](memory.md) |
| 可用性与生命周期 | 正式旅程离线只读、同步时间与失效边界；可定位反馈、用户说明、全域注销清理。CJ-022/023/024 [#24](https://github.com/JTCAO515/Go2China/issues/24)、[#15](https://github.com/JTCAO515/Go2China/issues/15)、[#27](https://github.com/JTCAO515/Go2China/issues/27) |
| UI 与双语 | Muse 四 Tab、记忆内账号、插件真实占位；中文/英文回答、错误、帮助、隐私和 VoiceOver 主要路径。CJ-006/026 [#7](https://github.com/JTCAO515/Go2China/issues/7)、[#29](https://github.com/JTCAO515/Go2China/issues/29) |

CJ-025～029 的故障、真实服务、恢复、效果/成本与受邀内测证据，以及 CJ-031/033 的公开首发准备仍是实际交付的一部分；规划完整不表示这些已通过。[完整范围与依赖](https://github.com/JTCAO515/Go2China/issues/5)。

## Non-goals

v1 不承诺多城市联程优化、实时机酒库存、自动预订付款、多人共编、插件市场/翻译、实时语音、图片/PDF 自动导入、安卓或完整 Web 客户端。Web 品牌名不构成 Web 实现范围。

人工托底与后台运营 Agent 是二三期方向，当前仅最小问题反馈，不承诺真人接管或真人外联。TypeSafeJev、多模型编排不作为已选首版栈。旧川剧熊猫/VisePanda 只作历史资产参考；不延用旧品牌，不因此删除旧资产。新账号策略不授权删除旧数据，也不继承旧权益。

## JT 待决清单

| 决定组 | 需要确定的最少内容 | 阻塞范围 / owner |
|---|---|---|
| 开工授权 | 对这套准备结果明确确认后才开始开发 | 全部产品开发；本轮尚未获得 |
| 首批使用边界 | 城市/行程范围、最低 iOS/设备、登录方式/受邀准入 | 只阻依赖该字段的实现和放行；CJ-001 [#1](https://github.com/JTCAO515/Go2China/issues/1) |
| 数据与验收口径 | 历史整理/敏感信息范围、离线可读时限、留存/清理说明、质量/延迟/成本指标与预算 | 对应数据处理、真实验证与公开首发；CJ-001/028 [#1](https://github.com/JTCAO515/Go2China/issues/1)、[#32](https://github.com/JTCAO515/Go2China/issues/32) |
| 商业与法律 | 免费/收费及档位；许可证、条款、隐私责任方/处理方 | CJ-030 [#6](https://github.com/JTCAO515/Go2China/issues/6)、CJ-031 [#34](https://github.com/JTCAO515/Go2China/issues/34)；收费明确后才启用 CJ-032 [#31](https://github.com/JTCAO515/Go2China/issues/31) |
| 入口与资产 | 角色名字/头像、礼物实际去向、附件/语音开放策略 | 仅阻最终资产/入口行为定稿，中性占位不阻布局；CJ-001/006 |

单城市 2–7 天、iOS 18、90% / 5 秒 / 90 秒都曾是助手建议，不是 JT 已批准限制或测试结果。技术候选按验证票收敛，不要求 JT 为每个常规实现细节重新审批。
