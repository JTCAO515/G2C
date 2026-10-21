# 两类入口：批准后执行的 runbook

以下为操作顺序，不是已运行结果。所有尖括号表示必须从批准对象/平台实际读回的值；没有已分配服务名、IP、域或证书。先完成 README 的 C2 源码缺口，固定候选并通过定向 Review/Testing，再允许设备/资源操作。HTTP/OpenAPI 保持现行边界，不切换 gRPC、不接未选 Agent/记忆。

## A — 受控局域网、本机 Python TLS

1. JT 批准指定手机、测试时间、同一局域网和本 M5 Pro 的一个实际网卡/IP/端口；记录端口初始占用。先确认网络允许设备互访；拒绝/客户端隔离时报告，不更改路由器、DNS/VPN、防火墙或扩大监听。没有批准，不启动 LAN listener。
2. 固定 C2 客户端/服务端配置：独立 `dev` 环境、精确 HTTPS origin、已选新 Auth ref/JWKS、TLS 证书路径、服务端新 DB 身份。环境名只是待实现值，当前 `CJ_ENV=local` 不支持该配置。服务端启动缺项即退出；不回落 VP、loopback 或生产。
3. 在仓库外批准的私有目录建立**该次实验专用** CA 和短期 leaf；leaf SAN 必须含批准的 IP/主机，CA/leaf 用途分开，私钥只在 M5 Pro。证书工具需按实际 LibreSSL/OpenSSL 版本帮助确认；本轮未生成/安装、也不提供把 OpenSSL3 命令直接套给 LibreSSL 的脚本。[OpenSSL req](https://docs.openssl.org/3.0/man1/openssl-req/)、[x509](https://docs.openssl.org/3.0/man1/openssl-x509/)。记录证书指纹/有效期，不记录私钥；只把公开 CA 证书交给批准手机操作者。
4. 指定测试手机安装该 CA 描述文件，并由操作者核指纹后启用 SSL/TLS 信任；这扩大该手机的根信任范围，需本次专项授权，不要求游客安装。Apple 路径是“设置→通用→关于本机→证书信任设置”。不把私钥交给手机，不给 Mac 全局根信任，也不使用跳过证书校验或广泛 ATS 例外。[Apple 信任说明](https://support.apple.com/en-us/102390)。
5. 仅批准网卡绑定 reviewed C2 factory，使用 uvicorn 已核到的 TLS flags。批准后的命令形状为：`uvicorn <REVIEWED_C2_FACTORY> --factory --host <APPROVED_LAN_IP> --port <APPROVED_PORT> --ssl-keyfile <PRIVATE_LEAF_KEY_PATH> --ssl-certfile <LEAF_CHAIN_PATH> --no-access-log`。这是不可直接运行的模板；当前 probe 入口不得代入。TLS 默认与链/域匹配须按目标 iOS 实测；不要绑定所有网卡或开公网转发。[uvicorn 官方设置](https://github.com/Kludex/uvicorn/blob/main/docs/settings.md)。
6. 如 iOS 要求本地网络授权，C2 工程补准确用途说明并由指定操作者允许；当前 C1 plist 未包含它，`NSAllowsLocalNetworking` 不代表用户已授本地网络权限。不请求 Bonjour 广播/发现，手工固定 origin；是否需要权限及拒绝行为列为设备验证项。[Apple 本地网络用途字段](https://developer.apple.com/documentation/bundleresources/information-property-list/nslocalnetworkusagedescription)。
7. 先验证严格 TLS/trace，再接全新 Auth、SMTP 和新 DB。仅本地 CA/Safari/probe 通过标记 A-transport PASS。新 Auth+DB+邮箱流程和跨用户矩阵没完成之前，C2 仍 UNRUN；即便完成同 LAN 联调，A 不证明蜂窝/异地持续可用，本提案不以 A 关闭完整 C2。

撤销边界：停精确 owned PID，确认该 IP/端口不再监听；移除该手机的本次 CA 描述文件和精确 dev URL/回调配置，复核不再信任；在批准留存/删除策略下处置实验私钥，不删除原钥匙串、其他描述文件或旧项目。退出局域网/证书过期/IP变化必须失败，不自动换地址、信任或公网入口。手机信任撤销步骤未实测。

## B — 隔离托管容器（具体参考 Cloud Run）

1. 批准实际新 GCP project、账单范围、region、运行身份、部署操作者和容器 registry；未盘点/未配置，不假定存在 Google 账户、CLI、额度或组织能力。候选服务名称、project ID 和 URL 在 `resource-request.json` 均为空。Cloud Run、镜像/secret/log 存储也计入资源和费用，不只批准“一个 API”。
2. 本地 reviewed C2 build 产出不可变镜像摘要，Python 依赖固定现有锁再加已接受 Auth/DB 依赖；不要从旧 VP 镜像/环境导入。Cloud Run ingress 容器按平台 `PORT` 在 `0.0.0.0` 监听，TLS 由平台终止；这只适用于容器内部，不能复制到 A 的 Mac listener。持久化只进入获准的新 Postgres，不把容器临时文件当业务/记忆/执行持久存储。[运行约束](https://docs.cloud.google.com/run/docs/container-contract)。
3. 配置仅该服务所需 secret 版本；runtime identity 只对精确 secret 有读取权限，部署身份与运行身份分开。迁移凭据只在批准的迁移操作短时可用，不进运行容器/App。选用 Secret Manager 时需单独批准该资源及 `roles/secretmanager.secretAccessor` 的限定绑定，不导出长期云 service-account 私钥。[secret 文档](https://docs.cloud.google.com/run/docs/configuring/services/secrets)。
4. 先以平台 Invoker IAM 校验保持关闭外部直接调用。普通 iOS 的 Supabase JWT 不是 Google Cloud 身份令牌；不能要求游客成为项目成员，也不能把 cloud admin token 放 App。若需要 App 直接访问，须额外批准该服务**平台层允许公网调用**及 ingress 范围，前提是 reviewed CJ 应用层已逐请求验证新 Supabase JWT、邀请/撤销、归属且 fail closed。Cloud Run 官方同时支持关闭 Invoker IAM 检查或给 allUsers invoker；本提案不执行/预选其中一种，不把它们说成已有权限。[平台访问文档](https://docs.cloud.google.com/run/docs/authenticating/public)。若组织不允许此模式，B 当前不满足直接设备入口，需新方案授权，不绕过组织策略。
5. 获准部署后从服务详情/describe 读回实际 `status.url`、revision、image digest、region、运行身份、配置指纹；只把**实际 HTTPS origin**写入获准 C2 客户端配置。Cloud Run 有稳定 HTTPS 地址并终止 TLS，原生入口无需自定义域；Supabase project/Auth URL 永远不当 CJ API 地址。[HTTPS 说明](https://docs.cloud.google.com/run/docs/triggering/https-request)。不依赖 HTTP→HTTPS 或 host 重定向，继续拒绝 API redirect。
6. 为 C2 规模单独批准 CPU/RAM、min/max instances、concurrency、timeout、DB pool 总连接上界；不在方案填未经测量的容量值。可提出 min=0、max=1 的小规模试验报价，但冷启动/SSE及DB行为要实测，max=1也不是费用硬上限。未接 RUN/SSE，本次不宣称托管已支持项目运行生命周期。
7. 在指定真实手机/目标 Wi-Fi与蜂窝网络执行 verification.md，记录实际地域/时间/网络、TLS、注册验证找回、邀请撤销、用户隔离及新库重开结果。大陆与游客来源网络到 Google/Supabase/SMTP 的可达性、延迟 UNKNOWN；不靠文档地域或 VPN 补造通过，也不为了网络问题更改主机配置。

撤销边界：先拒绝新增 CJ 请求/撤销测试资格与会话，停止该精确 dev 入口的平台公开调用/恢复 IAM；回退仅到已审且兼容新 DB 的 revision，不回退到无鉴权 probe。冻结/处置资源依明确预算与保留授权；停流量不等于镜像、secret、日志、DB停止计费。删除新项目、Auth用户、数据、镜像/secret或发信 DNS 均另属破坏性动作，不自动执行。不得改旧 VP 或全组织访问策略。
