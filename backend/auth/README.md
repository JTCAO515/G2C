# CJ 服务端 Auth 切片（内部可执行候选）

接口 `CJ-AUTH-SERVER@0.1.0-rc.1`，先行固定提交
`e49ea1a2abcdd82c93a28aeba8b2d6a1248a0f3b`；随后补本目录 JWT adapter 与独立锁。
源码基线 `29438a686fe631352ae0885ad3c9e6b7fbf0deb8` 的 Swift SDK 完全未改。
本包不是草案模型：实际调用 PyJWT/cryptography 校验签名与声明，提供可调用的内部
AdmissionChecker；但没有公开 API、实际身份/成员提供者、数据库或部署，不是生产验收。

新增显式 Supabase access profile 与 CJ005 可执行 composition 见
[API-COMPOSITION](../../contracts/auth/API-COMPOSITION.md)。原 strict 路径仍保留，
只有显式 opt-in 才采用新候选规则，不把本文原严格约束静默改为生产兼容保证。

## 接入面

- `cj_auth.interfaces`：TrustedPrincipal、VerificationResult、CJAccessProvider、
  AdmissionDecision；[完整接口/恢复约定](../../contracts/auth/SERVER-INTERFACE.md)。
- `cj_auth.jwt_adapter.PyJWTVerifier`：显式 JWTConfiguration 与 KeyProvider。
  不传配置或 key provider 时返回 UNKNOWN；不读环境变量/旧生产/凭据。
- `StaticPublicKeys`：仅服务端显式配置的 public PEM，构造时检查密钥类型/强度。
  kid 只查该映射；不把 header 里的 URL、嵌入 JWK 或任何用户数据当密钥来源。
  未知 kid 返回 UNKNOWN，以区别缺少轮换材料和已证实签名错误；不自动下载 JWKS。
- `AdmissionChecker.check(token)`：每次验证并重新查询服务端事实；当前身份 + CJ
  成员 + 邮箱验证 + 邀请均成立才 ALLOWED。资源归属由 CJ009 等领域继续核查。
  不接 caller owner/email/invited，不从 token 中同名字段或 user_metadata 授权。

CJAccessProvider 是既有权威的适配接口，不是第二名单库或并行权限源。当前没有真实
实现，默认无提供者时永不 ALLOWED。同 Supabase 项目的旧 VP token 即使通过 JWT
验证，也不能凭此成为 CJ 成员。测试中的事实提供者全部是局部合成替身。

## 本地 JWT 验证 profile

profile 是可审验实现约束，**不声称真实 provider 已兼容**；真实值/变更需确认。

- issuer/audience/algorithm/skew 均显式指定；一个验证器只允许 RS256 或 ES256
  中的一个固定算法，不按 token alg 决定允许集，不混 HMAC 与公钥算法。
- RSA 公钥至少 2048 位；ES256 仅 P-256；拒绝私钥、错误类型/曲线及坏公钥配置。
- 必须包含 iss、aud、sub、exp、iat、nbf。issuer 与单字符串 audience 精确匹配；
  subject 为非空字符串；时间为 JSON 整数（不接受 bool/字符串/浮点），exp 必须
  晚于 iat/nbf。PyJWT 验证 exp/iat/nbf 与签名；配置时显式指定允许时钟偏差。
  AdmissionChecker 在事实查询后以无宽限的 exp/nbf 再检查，不能因慢查询延长权限。
- header 必须 typ=JWT、非空 kid、匹配 alg；不接受其他 header 字段，包括
  jku/x5u/jwk/x5c/crit。不支持 detached payload。拒绝重复 JSON 成员、非对象
  payload、非有限 JSON 常量及超过本地 16 KiB 默认输入界限的 token。
- 格式、签名、明确算法/issuer/audience/时间错误 => INVALID；配置缺失、key
  未知/提供者失败 => UNKNOWN。失败不返回 principal 或原始异常/token。
  文本格式预检只负责歧义/类型拒绝，签名/标准声明验证交成熟库，不自造密码学。

本包的 VALID 不是“会话未撤销”承诺。没有 sid/revision/provider claim 的猜测，
没有真实 JWKS 更新、在线撤销/账户封禁、provider audience 映射或权限事务锁。
ALLOWED 仅是在本次边界上通过已配置验证与 provider 事实；实际接收/派发/提交
仍需相应消费者在自己的事务/异步边界复核，不是可永久缓存的 capability。

## 依赖、验证与复现

独立 `pyproject.toml` 固定 PyJWT[crypto]==2.15.1，`uv.lock` 固定全部依赖与发行物
hash；实际安装 cryptography 50.0.2、cffi 2.1.1、pycparser 3.11。不改根锁/工程。
官方 [PyJWT API](https://pyjwt.readthedocs.io/en/stable/api.html)要求独立配置算法
允许集，不能由 token 决定；本实现据此固定算法与 key 类型。
核对 [官方 changelog](https://pyjwt.readthedocs.io/en/stable/changelog.html)后使用
2.15.1，包含此前算法/key 混淆与输入解析修复，不调用 PyJWKClient 的远端获取。

在本目录执行：

```sh
UV_CACHE_DIR=/private/tmp/cj007-uv-cache uv sync --locked --python /opt/homebrew/bin/python3.14
.venv/bin/python -B -m unittest discover -s tests -v
```

Python 要求 >=3.12,<3.15，本次 macOS arm64 / Python 3.14.7。其他机器可选满足范围
的解释器，不依赖该绝对解释器路径。依赖下载只访问公共包仓库，与测试 Auth 网络隔离。
本轮首次受限网络解析 DNS 失败，公共依赖下载获工具审批后成功；未连接业务服务。

18/18 测试 PASS：6 项接口/准入 + 12 项 JWT/组合安全场景。日志 evidence/server-tests.txt；
接口首段日志 evidence/interface-tests.txt。测试 RSA/EC 私钥每次仅在内存生成，
不写磁盘、不打印 token/密码。覆盖真实本地签名、篡改/错误签名、issuer/audience、
none/HMAC、过期/未来/缺失/非法类型、重复 JSON、远端 key header、缺/坏 key provider、
未成员/邮箱/邀请未知和撤邀重查；关键组合测试禁用 socket，所有提供者为本地。
锁/安装版本与许可证元数据见 evidence/dependencies.json。没有真实 token 或私钥成果。

UNRUN：真实 provider/JWKS/在线撤销、实际 CJ 成员与邀请绑定、公开 API、数据库/RLS、
跨进程权限原子性、Google/Apple/C2、真机与部署。此切片不改原 AUTH/Swift 候选，
新接口消费者确认 PENDING；由 Main 路由 CJ009/独立 Review/Testing，不自行冻结或关票。

## VerificationResult P2 定向修复

差额 base `3f374214fefc820398f101f2ecbc086f83543eb5`：非 VALID 的 principal 严格
为 None；VALID 仍须 TrustedPrincipal。接口版本与 gate/JWT 逻辑不变。先在旧代码
执行新增 4 项回归，22 个错误类型子例 FAIL，日志 evidence/result-p2-before.txt（仅移除行尾空白，失败内容保留）。
修复后新增 4/4 与原准入 6/6 PASS，日志 evidence/result-p2-after.txt。原 18 项
证据保留；JWT adapter 未改，原 12 项密码学检查复用，未重复全量测试。
覆盖空/非空字符串、数值、bool、空/非空容器、任意对象、TrustedPrincipal、None、
VALID 合法/非法构造及错误 status 类型。未观察或声称修复前有 gate 越权。
CJ009 dc5352f 合法消费源码兼容；运行基线与真实分区/撤销/提交边界限制已明确写入
SERVER-INTERFACE.md，仍待原 owner 更新其固定消费引用/运行说明。

显式可选 JWKS provider/轮换候选见 [JWKS-PROVIDER](../../contracts/auth/JWKS-PROVIDER.md)。
默认无 transport/config 时仍 UNKNOWN、不联网；原 strict/静态公钥路径不变。
