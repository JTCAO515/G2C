# 登录前置回归：有 Lio 历史、没有旧 Demo starter

关联 [#1124](https://github.com/JTCAO515/G2C/issues/1124)、
[#1048 真实冒烟回执](https://github.com/JTCAO515/G2C/issues/1048#issuecomment-6935416253)。
本文件新增回放定义，不修改旧 25 例、14 项冒烟分母、冻结契约或既有失败记录。
下面两个语言变体均为 **UNRUN**，不能拿 2026-11-17 中文登录失败当成英文执行结果。

## 原观察与归属

2026-11-17，窗口 `manual14-20261117T013623Z`；A 模拟器 Beta 0.1.0(46)，
客户端源 `e4ea8198fcb5fc0ffe69a937458386fb2f9aba82`，服务器源
`b804fe8fd8cadf721f2bacc3d461499ae9a8cece`、schema55、镜像
`sha256:ba211e2c7961a676be34a71f1a3cf708c9373ece7a20738f7bf5b81b9874e96f`。

JT 正式手输登录后没有进入 Home。两次邀请签发 POST 均 HTTP200，各自后续三个 GET
也均200；最后仍显示“暂时无法登录请检查网络后重试”。这只证明服务器收到请求，
不证明用户登录完成。没有业务 MESSAGE，七项中英 14 条全部 UNRUN，登录前置单列 FAIL。

B 只读元数据确认：既有合成身份有 25 个活动对话，但首20与全部25都没有
`demo-starter-zh`，对应 NEEDS、旅行上下文 starter 也没有。不能归因于第21条后的分页。
客户端 `DemoStarterReads.profile` 要求旧 starter 三件套；实际根因、修复范围由 A/B
在 #1124 核对。本文件不宣称问题已修复，也不向账号补造旧 starter。

## LOGIN01：已有 Lio 身份不以旧 starter 作为用户登录成功的证明

| 项目 | 中文变体 | English variant |
| --- | --- | --- |
| 界面语言 | 中文 | English |
| 合成前置 | B 签发且只读核定同一既有 Lio 合成身份；有正常历史，无旧 Demo starter 三件套 | B signs and verifies an existing synthetic Lio identity with real history and no legacy Demo starter trio. |
| 输入 / 任务 | 使用正式邀请登录，进入原账号 Home，查看已有对话 | Sign in with the official invitation, reach Home for the same account, and inspect an existing conversation. |
| 期望 | 实际进入 Home，账号与历史不变；不得仅因缺旧 starter 错报网络错误或制造新历史 | Reach Home for the same identity with history preserved; missing legacy starter data must not produce a misleading network error or fabricated history. |
| 判定 | A 提供实际 Home 和历史可见证据；C 核身份、实际请求引用及服务端历史；两侧一致才 PASS | PASS only when A observes the actual Home/history and C verifies the matching identity, request references, and server history. |

- A 使用普通用户流程，登录动作、客户端错误时点与服务器 request reference 分开记录。
  C 只读原件，不能拿成功 POST、GET、欢迎语或本地缓存页面单独判 PASS。
- 若登录未完成，单列前置 FAIL/UNKNOWN，随即停新；SM01–SM07 及另一语言剩余项
  保持 UNRUN。不连续重试，不清状态、换账号或注入 starter 掩盖同一失败。
- 不读取、打印、截图或写入邀请码、token、密钥；有输入框残留秘密时只收安全元数据。
- A/B 的本地测试可以覆盖缺 conversation、NEEDS、travel 的独立分支；这些是 L0/L1
  控制，不能冒充真实香港结果。真实回放只在新部署、新窗口、新阶段 ID 下执行，
  使用 C 既有子额度，23:00–08:00 禁合成请求。
- 登录恢复后仍需继续中英七项实际冒烟；本例通过不能替代问答正文、实际三日行程、
  历史恢复、后台返回或费用原件。随后按 L 基础8条 → C 全国16条的原顺序推进。

## 证据与费用

真实回放报告分别登记输入语言、App build/source、服务器 source/image、身份绑定摘要、
实际 POST/GET 引用、UI结果、MESSAGE/RUN（若没有则明确无业务消息）、
首进度/首正文/完成时间和三栏费用。未到业务步骤的时间为 UNRUN，不能用登录 HTTP
耗时替代正文耗时。未知实付保留 UNKNOWN，旧尝试的 FAIL/UNKNOWN 与费用不回填。

原窗口已因前置失败关闭并回滚到 `2e5560cf3c794df4aff48c8431e8424330580e10`；
新回放不能沿用它的租约、旧原件或成功断言。修复后结果在 #1124 与 #1048 分别登记。
