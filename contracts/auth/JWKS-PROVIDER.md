# CJ-JWKS-PROVIDER@0.1.0-rc.1 — 有界轮换公钥提供者候选

base `6f5c60d097240b12b4a910fa989decfd3312567c`；源码
`backend/auth/cj_auth/jwks_provider.py`，遵循现有 KeyProvider.resolve(kid)。
仅增加可选注入实现，不改 PyJWTVerifier、strict 默认、旧 JWT profile、成员准入或
共享 API。新候选待独立审验及 host 消费确认，未发布为完整 AUTH。
Keychain 单次签名/启动失败状态不变，本轮未 sign/launch/读写 Keychain。

## 精确 host 注入

```python
provider = BoundedJWKSProvider(verification=explicit_jwt_configuration,
                              configuration=explicit_jwks_configuration,
                              transport=host_transport)
verifier = PyJWTVerifier(explicit_jwt_configuration, provider)
```

参数是 host 获准配置，不是预填地址或可运行的真实服务凭据。缺 verification、
JWKS 配置或 transport，resolve 返回 None，由原验证器映射 UNKNOWN，**不联网**。
源码没有 requests/urllib HTTP client、PyJWKClient、默认项目 URL 或后台刷新任务。

JWKSConfiguration 的全部策略字段必须显式传入：issuer、固定 HTTPS url、algorithm、
cache_ttl_seconds、refresh_interval_seconds、request_timeout_seconds、max_response_bytes、
max_chunks、max_keys、max_kid_bytes、max_rsa_bits。时间必须正数且有限，计数为正整数，
RSA 上限不能低于已有 2048-bit 下限。测试值只是 fixture，不是推荐产品值。
JWT clock_skew_seconds 仍由原 JWTConfiguration 显式提供，JWKS TTL 不扩张 token 寿命。

构造时必须核配置 issuer/algorithm 与传入 JWTConfiguration 完全一致；URL 必须
HTTPS，无 userinfo/query/fragment/空白。host 绑定可信 issuer 到固定 URL，可为
独立可信域，但不得把 token 的 jku/x5u/任意 URL 用作配置。原 verifier 的 header
拒绝规则保持。一个 issuer/profile 的 provider 应在 host 中复用，不能每请求重建
来绕开冷却；限流是**每 provider 实例/进程**，不是跨 worker 分布式限流承诺。

## transport、解析与错误边界

JWKSTransport.fetch(JWKSRequest) 返回 JWKSResponse：status、final_url、content_type、
分块 bytes iterable 与 close()。host transport 必须执行连接/读取期限、响应字节
上界、取消事件并**禁止跟随重定向**；provider 同时要求 200、final_url 精确等于
配置 URL、JSON/JWK-set 媒体类型，按字节/分块数限界读取并始终 close 响应。
重定向后的 URL 核对是额外防线，不授权 transport 先访问任意重定向目标。

同步接口不能强制打断不合作的阻塞 fetch/iterator/close：本实现检查各读取边界与
返回后的 deadline、取消，并拒绝晚到结果；真实 transport 的硬超时及资源关闭
仍需实际 host 验证。无效 transport 不得因测试替身及时返回就标真实网络 ready。

解析拒绝重复 JSON 字段、非对象/非 keys 数组、超 key 数、缺/重复/超长 kid、私钥
字段或对称 secret。只接显式配置 alg；集合中其他算法的公钥忽略，不自动扩算法。
匹配 alg 的 key 必须 kty 相符、用途 sig、key_ops 仅 verify（缺省按 JWK 可选字段
处理）。PyJWT 2.15.1 PyJWK 解公钥，再复用 VerificationKey.load 的 RSA 强度/P-256
约束与配置 RSA 上限。候选集完整验证后一次替换，不发布半份坏集合。

坏响应、未知 kid、网络/解析失败、取消、超时、缺配置均返回 None → UNKNOWN，
不把服务依赖异常当 INVALID。只有原 verifier 拿到可信 key 后证实签名/声明不符
才 INVALID。仍沿用 entry UNKNOWN 的 unknown/retry_safe_read，仅安全验证/查询；
不授 POST 重发/模型执行权，不覆盖原动作 reconcile_original。

## 缓存、轮换与并发

- 缓存只保留验证后的公钥材料；有效期从**刷新开始时**计算。慢响应不延长 TTL，
  失败刷新不续期；过期后即使内存仍有旧公钥也不返回，不做无限 stale fallback。
- 有效命中不请求 transport；未知 kid 或到期可触发一次刷新。所有 kid 共用正的
  refresh interval，恶意随机 kid 不创建无限负缓存/刷新请求。冷却期返回 UNKNOWN。
- 一个实例同一时刻最多一个刷新；其他 miss 并发调用立即 UNKNOWN，不排无限等待队列。
  已有未过期命中仍可用。网络调用不持有 cache lock，避免堵塞取消/关闭。
- 成功集合原子替换，已移除 key 不继续保留；新 kid 轮换受全局冷却约束。重用同 kid
  的换 key 只能在 TTL/另一次合法刷新后观察到；签名失败不会额外触发网络刷新。
  刷新前的新签名可能 INVALID，这是已知公钥快照边界，不宣称实时轮换无窗口。
- cancel_refresh 取消当前请求，不重置冷却、不接受其晚到结果；close 永久关闭此
  provider、清 cache 并取消在途。取消后重新刷新仍受原冷却；close 不自动复活。
- 这些不是实时 session 撤销。host 仍需独立 CJ 成员/邮箱/邀请事实与提交边界校验；
  不缓存 ALLOWED、不把下载到公钥当作会话/成员/数据库权限验收。

## 本轮实际证据

12 项新增本地测试 PASS，日志 `backend/auth/evidence/jwks-tests.txt`：真实本地签名
与缓存命中；不同 kid / 同 kid 轮换；未知 kid 洪泛与失败冷却；TTL 到期失败不回退；
字节/块数/kid/key 数、重定向与响应关闭；重复/私钥字段/算法类型/用途拒绝；EC 曲线；
并发单刷新；取消/close 晚到；deadline/时钟回退。测试 key 仅内存生成，transport
仅返回本地公钥 JSON 或合成故障，没有真实 Supabase/旧项目/provider/JWKS 请求。

复现（backend/auth 目录，现有独立锁环境）：
`.venv/bin/python -B -m unittest discover -s tests -p test_jwks_provider.py -v`。
本机 Python 3.14.7；包 >=3.12,<3.15。既有 JWT/准入源码和依赖锁未变，原签名/类型/
composition 证据复用，不重跑无关 Keychain/Swift/数据库测试。

当前没有真实 transport、JWKS 缓存共享/跨进程限流、DNS/TLS/重定向实际网络验证、
真实轮换/撤销或 RLS 结果；这些保持 UNRUN。仅供 CJ005 在获准 host composition
中明确注入的新候选，不改根锁/路由，不声明真实服务已经接通。
