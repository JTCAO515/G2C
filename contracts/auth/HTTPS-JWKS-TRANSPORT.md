# CJ-JWKS-HTTPS@0.1.0-rc.1 — 可选显式 HTTPS transport 候选

base ddbe4367f34480a5822465777559323e28067279。实现
`backend/auth/cj_auth/https_jwks_transport.py`，兼容原 JWKSTransport.fetch(JWKSRequest)。
原 provider/JWT/strict 策略源码不变，默认仍没有 transport/配置，不联网。新候选
待独立审验，不代表真实 Supabase/外网 DNS/TLS、C2 或账户已验收。Keychain 未动。

## 技术选择与具体注入

包内 exact HTTPX **0.28.1**，uv.lock 固定 httpcore/anyio 等传递依赖；根锁不动。
官方 [HTTPX timeout](https://www.python-httpx.org/advanced/timeouts/)区分连接、读取、
写入和连接池超时；这些是网络层控制，不以 provider 返回后的 deadline 检查替代。
[HTTPX API](https://www.python-httpx.org/api/)提供显式 TLS、重定向和 trust_env 参数。

HTTPSConfiguration 要求完整 canonical HTTPS URL、connect/read/write/pool timeout、
cancellation_poll_seconds、max_response_bytes、max_chunks 全部显式配置。缺配置时
fetch 抛安全 disabled；目标 URL 与 host 配置不完全相等时，在 I/O 前拒绝。
不接受 token URL、userinfo/query/fragment、规范化会改变目标的 URL 或默认项目。

```python
transport = HTTPSJWKSTransport(explicit_https_configuration)
provider = BoundedJWKSProvider(verification=explicit_jwt_configuration,
                              configuration=explicit_jwks_configuration,
                              transport=transport)
```

host 必须让两份配置的 JWKS URL 一致；不一致会安全 UNKNOWN，不猜 fallback。
默认 SSL 验证启用；可注入 host 自有 SSLContext，但必须 CERT_REQUIRED 且 check_hostname。
测试自签 CA 只放入局部 SSLContext，绝不修改系统信任。注入后的 context 不得再由其他
代码修改成不验证模式。没有 verify=False 参数、代理/认证/cookie 或客户端 secret 配置。

同步 fetch 仅可在无活动 asyncio loop 的受控 worker 调用；已有 loop 上直接调用
明确拒绝，防止嵌套 loop/阻塞异步 host。内部 asyncio.run + AsyncClient 执行一次
GET：trust_env=false、follow_redirects=false、retries=0、独占单连接且不保留连接。
不读取环境代理/证书覆盖/netrc。禁止所有 3xx 的实际跟随；返回状态元数据供原
provider 拒绝，既不解析 Location 作授权，也不访问重定向目标。

## 时限、取消与有界响应

- HTTPX 的 connect/read/write/pool timeout 取显式配置与请求总时限的较小值，真实
  网络 I/O 使用这些值；连接超时包括本轮验证的 TLS handshake 停滞路径。
- asyncio.timeout 包围网络任务，慢速持续滴流不能靠不断产生字节绕过总任务时限。
  独立 async watcher 观察原 request.cancelled，取消在途网络 task；finally 等待
  task 收尾并关闭 stream/client，无后台刷新、重试线程或遗留监听。
- **DNS 边界仍未验**：真实测试只使用 127.0.0.1。平台 resolver/线程池收尾及
  asyncio.run 在 OS DNS 阻塞下的同步返回总上界没有证明，不能声称所有 DNS/平台
  情况都具硬墙钟返回保证。实际域名 host 必须补有界 resolver/worker 取消与关闭
  证据；注入的 async transport 也不能用同步阻塞实现逃避 event-loop 取消。
- 请求 Accept-Encoding=identity；压缩响应拒绝，不执行无界解压。读取 aiter_raw
  的网络分块，在累积前检查字节数/块数；body 上界取请求值与 adapter 值的较小者。
  header 的协议解析使用固定 HTTP 客户端，body 限制不冒称全进程内存硬上限。
- fetch 返回前网络 stream/client 已关闭，仅留下有界 BufferedJWKSResponse；其
  close 清除 body chunk 引用。原 provider 仍独立检查状态、URL、类型、字节与 TTL。
- 异常只有安全理由（disabled、target_mismatch、connect_timeout、read_timeout、
  total_timeout、cancelled、body_limit、request_failed 等），不暴露 URL/原异常正文/
  response bytes。provider 统一映射 UNKNOWN，不据网络故障判断凭据无效或重发业务。

## 验证分层与复现

在 backend/auth，Python 3.14.7 / 独立锁环境：

```sh
.venv/bin/python -B -m unittest discover -s tests -p test_https_transport.py -v
.venv/bin/python -B -m unittest discover -s tests -p test_jwks_provider.py -v
# 明确批准 loopback 测试时才设置此开关：
CJ_AUTH_LOOPBACK_TLS_TESTS=1 .venv/bin/python -B -m unittest discover -s tests -p test_https_loopback.py -v
```

- **8/8 注入 HTTP transport PASS**：默认关闭、固定目标、预取消、无 secret headers、
  HTTPX 超时参数、所有常见 redirect 零跟随、限界/压缩拒绝、adapter 内部总时限、
  在途取消与关闭、TLS 禁止降级、已有事件循环拒绝。evidence/https-transport-tests.txt。
- **7/7 真实 loopback TLS PASS**：局部 CA 信任下 TLS→JWKS→本地 JWT 验签；实际
  302 的 target 零请求；未信任证书在 HTTP 前失败；真实阻塞 body 的 read timeout；
  慢速滴流 total timeout；在途取消早于长 read timeout；原始 loopback listener
  停滞 TLS handshake 的 connect timeout。evidence/https-loopback-tests.txt 保存
  实际耗时、各监听关闭、临时证书目录已删除记录。测试只监听 127.0.0.1 随机端口。
- loopback fixture 全部来自新临时目录/内存，TLS key 与 JWT signing key 分开；
  未安装系统 CA、未改安全设置。每测试关闭 server/socket、join worker，最终移除
  临时证书；无长期服务。未使用真实 token、provider、项目或账号。
- 默认没有 CJ_AUTH_LOOPBACK_TLS_TESTS=1 时该组 **7项 SKIP**，不会 bind/listen，
  证据 https-default-no-listener.txt；普通全量发现不会偷偷启动 TLS 服务。
- 原 **12/12 JWKS provider 回归 PASS**（新依赖图下定向运行），证据
  https-provider-regression.txt。旧 JWT 签名/准入逻辑未改，其他已有证据复用。

外网 DNS、真实 CA/生产域名、Supabase JWKS、真实代理环境/地区网络、在线轮换与
撤销、数据库/RLS、部署和真机全部 UNRUN。新版本只解决可注入 HTTPS I/O 切片，
不允许借测试结果开启正式网络/权限出口；独立审验由 Main 路由。

## 同轮 CJ005 history/draft 只读确认

已核 `history-draft-proposal.md` SHA-256
1417a8173a3bd7101a2ad48d052f3ba6d8acce158bdb3511374ae0060ff814c8。
固定 AUTH79f88b 的可信 issuer/subject/audience 与同一次 server context 的 env/scope
可用于 cursor 绑定；不能从 decoded cursor 选仓储或拼接两次无绑定鉴权。持久分区
不含 token 时间；刷新后同身份/scope/query 可按显式 cursor TTL/版本政策继续读，
若 codec 选择绑定旧 token 可保守 resync。不存在 session revision/撤销版本，不能
承诺刷新/退出自动撤销所有旧 cursor。read resync 409 failed/retry_safe_read 兼容；
unknown 不授写重试；draft commit/return 未知 reconcile_original 查询原 draft/version，
不凭内容相等认定提交者。StableBoundary 具体接缝由 CJ009 确认；无需等待 transport。
