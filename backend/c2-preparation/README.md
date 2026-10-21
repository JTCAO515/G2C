# CJ-005 C2 准备候选：设备 HTTPS、全新 Auth / 数据

2026-10-21（北京时间）。准备基线 `ec05c2727dd40c7ed130d7214d367207a000c9f2`，原分支 `cj/005-foundation`，开工时 clean。本目录只含方案与登记；不是配置、资源申请或执行脚本。requested：项目默认 gpt-6.1-sol / medium；effective：UNKNOWN。

## 当前结论

建议先用 A 验证指定手机的本地 HTTPS / 回调实现；需要跨 Wi-Fi/蜂窝的内测入口时再批准 B。A 单独不能满足完整 C2；B 是可以承载完整 C2 的候选，但同样必须接通**全新 Supabase Auth + Postgres、JT 邀请名单与真实邮件验证/找回**并通过设备验证，创建一个 HTTPS 地址不算完成。当前两者均 UNRUN。

| 项目 | A：指定局域网 + 本地 TLS | B：隔离托管 Python API（参考候选 Google Cloud Run） |
|---|---|---|
| API 执行位置 | 本 M5 Pro，指定网卡 IP/端口，仅批准设备可达；不映射公网 | 单独新云项目/运行身份内的容器；不复用 VP 或其他项目 |
| TLS | 新建短期实验 CA + 匹配局域网 IP 的服务证书；仅指定测试手机手动信任 | 平台提供稳定 HTTPS 端点/TLS；不预造 run.app URL，不要求先买自定义域 |
| 入口边界 | 同一批准局域网；Mac 休眠/网络变化会中断 | 设备能访问托管 HTTPS；网络/地域实测之前可达性 UNKNOWN |
| 用途 | 首次手机 TLS、SDK、确认/找回回跳；设备/证书需专项批准 | 可承载新账号→CJ API→新 DB 的 C2 跨网络联调 |
| 独立不足 | 仅本地网络开发证据；不证明蜂窝、异地游客、持续在线 | 仅托管不等于鉴权；必须有应用层 JWT/邀请校验、数据隔离、邮件与回调 |
| 是否现在执行 | 否 | 否 |

Cloud Run 是有官方 Python/容器与 HTTPS 文档的产品示例，不是项目已接受的部署平台；若批准其他托管商，保留本目录的验收条件、重核其具体运行/账单事实，不能把这里的 Google 参数套用到其他服务。[Cloud Run HTTPS](https://docs.cloud.google.com/run/docs/triggering/https-request)、[容器运行约束](https://docs.cloud.google.com/run/docs/container-contract)。

## 已确认输入、建议与未知分开

本轮派工明确：邮箱密码、自助注册、验证与找回、JT 邀请名单；旧 VP 不复用。上游盘点转交“未发现专用 CJ 环境”，本轮没有再读账户资源清单，不能据此断言全账户不存在任何资源。`cj-dev` 是待建候选名称，非已创建 ref。Go2China Pro 组织、Singapore 是建议，未获选定/创建授权；计费余额、税费、配额、增量报价 UNKNOWN。

官方事实：默认 SMTP 限组织团队成员，当前每小时 2 封且无交付 SLA；自定义 SMTP 初始每小时 30 封，仍需检查配置/供应商限制。这不能通过把游客加入项目团队解决。需批准独立 SMTP 供应商、发信域/From、DNS 变更、收件人范围与费用，游客仅为 App 用户。[SMTP 官方说明](https://supabase.com/docs/guides/auth/auth-smtp)。

## 当前源码缺口

在固定基线核对：`backend/cj_api/app.py:create_app` 仅接受 `CJ_ENV=local`，只有不带 Auth 的只读 probe；`ProbeConnection` 只接受 HTTP literal loopback，拒绝重定向；没有 Supabase/JWT/邀请名单/DB adapter、HTTPS 设备配置、回调处理或邮箱密码页面。现有 PostgreSQL `0001` 只建立迁移账本，未应用。**不能把 probe 直接开放到 LAN/托管，或仅替换 CJ_API_BASE_URL 就称 C2。** 本轮不改这些源码/锁/工程；下一实施 lease 必须覆盖对应实现，AUTH@1.0 仍由 CJ-007 收敛，不在准备资料里冻结新业务路径。

## 材料与下一次批准包

- [执行顺序与 HTTPS 入口](https-plans.md)：两方案各自前置、拟执行动作、成功标志、撤销。
- [Auth、环境、角色和费用](auth-environment-cost.md)：安全交接位置、回调、名单、身份、账单来源及未知。
- [设备验证与证据口径](verification.md)：逐项 PASS/FAIL/UNRUN，不能用 mock、Safari 页面或 /probe 代替完整联调。
- [未分配资源清单](resource-request.json)：实际 ID/URL/预算均为空；这是提案，不会被现有程序读取。

下一批准包最少需：A/B 选择与测试网络/设备；全新 Supabase 的组织/项目/数据库引擎/地域/账单上限；SMTP 供应商/域与邮件预算；邀请名单安全来源和维护/撤销责任；C2 实现 owner 与文件 lease；若 B，还需云项目/平台/地域/运行身份/入口权限与费用控制。先收集拟创建资源的实际报价供 JT 审批，再执行；不默认已有信用抵扣、免费额度、外部发信或公开入口权限。

## 本轮证据

PASS：官方公开文档读取（Supabase docs connector + web；未查询/写项目）、原源码只读差额核对、文档/JSON 与写权检查。已在本机只读核到 `/usr/bin/openssl` 为 LibreSSL 3.3.6，现有 uvicorn CLI 提供 TLS key/cert 选项；OpenSSL 3 示例不能直接当本机 LibreSSL 已兼容。本轮不生成证书、不装 CA、不运行服务器、不解析/探测拟建端点、不发邮件、不安装工具、不填凭据、不创建云资源。

已按 Supabase skill 读官方 changelog 索引；网页工具不支持 Markdown content-type 后，仅用只读 HTTPS 获取索引并检查相关 breaking change。2026-10-12 公告称最早 2026-11-10 停用部分旧 TLS1.2 CBC 套件；设备矩阵需要实测，不能由本机 SDK 构建推断支持。其他语言 SDK/自托管网关公告不表示本方案采用它们。[TLS 公告](https://supabase.com/changelog/cbc-tls-ciphers-deprecated)。

C2 资源、SMTP/注册/确认/找回、真实账号隔离、新库初始化/回退、HTTPS 设备、托管、费用及产品验收全部 UNRUN。保留原 C0/C1/R1 候选证据，不重跑无关检查，不关 Issue #5。
