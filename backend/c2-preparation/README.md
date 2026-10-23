# CJ-005 C2 当前收口入口

2026-10-23（北京时间）。当前基线 `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`。
先读 [最短 C2 收口方案](C2-CLOSURE-PLAN.md)、[具体授权提案](c2-approval-packet.json) 和 [本轮只读事实](evidence/2026-10-23-readonly-state.json)。

当前推荐：**全新 Go2China-org Supabase/Singapore + Cloud Run/Singapore 平台HTTPS + Resend Free + C2原生配置**。未获准创建/费用/公网入口/SMTP/DNS/签名设备权限，C2及PR62 apply仍BLOCKED。当前两个可见连接只列旧VP项目，未发现新CJ目标；其他账户UNKNOWN，不据此断言无资源。

最新不使用旧库/不迁移旧账号数据的范围覆盖下方历史“先旧VP评估”的顺序。历史“仅probe、无JWT/DB adapter”的源码描述也已过时；当前可复用源和准确尚缺的C2 profile/live facts/session/callback/managed迁移接线见新方案。本轮只做准备，不计产品编码，不创建/修改/启动资源，不关闭Issue5。

## 2026-10-21 历史准备原文（保留，当前执行顺序以上述收口方案为准）

# CJ-005 C2 准备候选：设备 HTTPS、身份 / 数据隔离

2026-10-21（北京时间）。准备基线 `ec05c2727dd40c7ed130d7214d367207a000c9f2`，原分支 `cj/005-foundation`，开工时 clean。本目录只含方案与登记；不是配置、资源申请或执行脚本。requested：项目默认 gpt-6.1-sol / medium；effective：UNKNOWN。

## 当前结论

最新资源优先级：先只读评估旧 VP-V4（已有61个public authenticated函数，共享环境隔离尚未放行，与邀请注册门禁无关）；不满足隔离/冲突门槛时，再提交收费新 CJ 项目的具体批准包。入口层建议先用 A 验证指定手机的本地 HTTPS / 回调实现；需要跨 Wi-Fi/蜂窝的内测入口时再批准 B。A 单独不能满足完整 C2；B 是可以承载完整 C2 的候选，但同样必须接通**经批准的 CJ 身份/数据隔离、JT 邀请名单、邮箱验证/找回及 Google/Apple 登录**并通过设备验证，创建一个 HTTPS 地址不算完成。当前两者均 UNRUN。

| 项目 | A：指定局域网 + 本地 TLS | B：隔离托管 Python API（参考候选 Google Cloud Run） |
|---|---|---|
| API 执行位置 | 本 M5 Pro，指定网卡 IP/端口，仅批准设备可达；不映射公网 | 单独批准的云项目/运行身份内的容器；不复用旧服务运行权限 |
| TLS | 新建短期实验 CA + 匹配局域网 IP 的服务证书；仅指定测试手机手动信任 | 平台提供稳定 HTTPS 端点/TLS；不预造 run.app URL，不要求先买自定义域 |
| 入口边界 | 同一批准局域网；Mac 休眠/网络变化会中断 | 设备能访问托管 HTTPS；网络/地域实测之前可达性 UNKNOWN |
| 用途 | 首次手机 TLS、SDK、确认/找回回跳；设备/证书需专项批准 | 可承载 CJ 账号→CJ API→隔离数据的 C2 跨网络联调 |
| 独立不足 | 仅本地网络开发证据；不证明蜂窝、异地游客、持续在线 | 仅托管不等于鉴权；必须有应用层JWT/归属校验、受限访问/派发资格校验、数据隔离、邮件与回调 |
| 是否现在执行 | 否 | 否 |

Cloud Run 是有官方 Python/容器与 HTTPS 文档的产品示例，不是项目已接受的部署平台；若批准其他托管商，保留本目录的验收条件、重核其具体运行/账单事实，不能把这里的 Google 参数套用到其他服务。[Cloud Run HTTPS](https://docs.cloud.google.com/run/docs/triggering/https-request)、[容器运行约束](https://docs.cloud.google.com/run/docs/container-contract)。

## 已确认输入、建议与未知分开

最新派工覆盖原“新建优先”：邮箱密码、自助注册、验证与找回、JT邀请仅控制受限业务/模型，账号注册/验证/登录/找回不受其阻断，加Google/Apple；优先旧 VP-V4 的只读隔离评估，次选收费新项目。不复制旧凭据、不继承旧账号/数据、不恢复 VP 开发。用户当前不在电脑，需亲自完成的控制台/2FA/设备步骤先标 SKIP-pending-human，继续独立准备。上游首轮盘点“未发现专用CJ环境”，仅覆盖可见连接；其后已复用支持线程的VP-V4精确只读metadata，见旧项目评估，不据此断言其他账户无CJ环境。`cj-dev` 是待建候选名称，非已创建 ref。现有VP-V4所属Go2China组织/Pro计划与Singapore已由metadata确认；收费新CJ项目的组织归属、地域选择与创建仍未批准；Main转交已取官方get_cost的假设报价 monthly USD10，未获费用批准；本owner未读取原报价回执，不把它当最终含税/总账单承诺。计费余额、税费、配额及最终增量仍需核对。

官方事实：默认 SMTP 限组织团队成员，当前每小时 2 封且无交付 SLA；自定义 SMTP 初始每小时 30 封，仍需检查配置/供应商限制。这不能通过把游客加入项目团队解决。需批准独立 SMTP 供应商、发信域/From、DNS 变更、收件人范围与费用，游客仅为 App 用户。[SMTP 官方说明](https://supabase.com/docs/guides/auth/auth-smtp)。

## 当前源码缺口

在固定基线核对：`backend/cj_api/app.py:create_app` 仅接受 `CJ_ENV=local`，只有不带 Auth 的只读 probe；`ProbeConnection` 只接受 HTTP literal loopback，拒绝重定向；没有 Supabase/JWT/邀请名单/DB adapter、HTTPS 设备配置、回调处理或邮箱密码页面。现有 PostgreSQL `0001` 只建立迁移账本，未应用。**不能把 probe 直接开放到 LAN/托管，或仅替换 CJ_API_BASE_URL 就称 C2。** 本轮不改这些源码/锁/工程；下一实施 lease 必须覆盖对应实现，AUTH@1.0 仍由 CJ-007 收敛，不在准备资料里冻结新业务路径。

## 材料与下一次批准包

- [执行顺序与 HTTPS 入口](https-plans.md)：两方案各自前置、拟执行动作、成功标志、撤销。
- [Auth、环境、角色和费用](auth-environment-cost.md)：安全交接位置、回调、名单、身份、账单来源及未知。
- [设备验证与证据口径](verification.md)：逐项 PASS/FAIL/UNRUN，不能用 mock、Safari 页面或 /probe 代替完整联调。
- [Google/Apple与人工步骤](providers-and-human-steps.md)：邮箱与原生/浏览器OAuth资源、回调、可先做代码。
- [旧VP-V4只读评估](vp-v4-readonly-assessment.md)：待支持盘点的分类/依赖/恢复门槛，不重复读敏感数据。
- [未分配资源清单](resource-request.json)：实际 ID/URL/预算均为空；这是提案，不会被现有程序读取。

下一批准包最少需：A/B 选择与测试网络/设备；VP-V4只读盘点与隔离可行性；若不满足，再申请新Supabase的组织/项目/数据库引擎/地域/账单上限；SMTP 供应商/域与邮件预算；邀请名单安全来源和维护/撤销责任；C2 实现 owner 与文件 lease；若 B，还需云项目/平台/地域/运行身份/入口权限与费用控制。先收集拟创建资源的实际报价供 JT 审批，再执行；不默认已有信用抵扣、免费额度、外部发信或公开入口权限。

## 本轮证据

PASS：官方公开文档读取（Supabase docs connector + web；未查询/写项目；旧VP元数据盘点由支持线程执行，本owner只复用本地报告）、原源码只读差额核对、文档/JSON 与写权检查。已在本机只读核到 `/usr/bin/openssl` 为 LibreSSL 3.3.6，现有 uvicorn CLI 提供 TLS key/cert 选项；OpenSSL 3 示例不能直接当本机 LibreSSL 已兼容。本轮不生成证书、不装 CA、不运行服务器、不解析/探测拟建端点、不发邮件、不安装工具、不填凭据、不创建云资源。已复用旧VP只读metadata并生成保守对象分类，未删除或更改任何对象。

已按 Supabase skill 读官方 changelog 索引；网页工具不支持 Markdown content-type 后，仅用只读 HTTPS 获取索引并检查相关 breaking change。2026-10-12 公告称最早 2026-11-10 停用部分旧 TLS1.2 CBC 套件；设备矩阵需要实测，不能由本机 SDK 构建推断支持。其他语言 SDK/自托管网关公告不表示本方案采用它们。[TLS 公告](https://supabase.com/changelog/cbc-tls-ciphers-deprecated)。

C2 资源、SMTP/注册/确认/找回、真实账号隔离、新库初始化/回退、HTTPS 设备、托管、费用及产品验收全部 UNRUN。保留原 C0/C1/R1 候选证据，不重跑无关检查，不关 Issue #5。

最新范围补充以本目录 `providers-and-human-steps.md` / `vp-v4-readonly-assessment.md` 为准。任何原文“全新项目”为隔离更强的收费备选方案；不表示跳过旧VP优先评估或已经获建项目授权。
