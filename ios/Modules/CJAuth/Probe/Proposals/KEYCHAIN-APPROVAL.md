# CJ007 专用模拟器最小签名/entitlement 变更提案 — 尚未执行

## 已核事实与准确对象

- 工程形式：包内独立 `Probe/build.sh` 直接 swiftc 编译的 module/产物
  **CJ007SessionProbe**，不是根 Xcode 工程 target。
- 库目标：已有 CJSession；新准备的 CJMessageKeys。probe 源码现可编译两者，
  本轮只做 typecheck，**没有重建/重签/重新安装现有 .app**。
- bundle ID / codesign Identifier：`local.g2c.cj007.sessionprobe`。
- 现有产物：`ios/Modules/CJAuth/Probe/.build/CJ007SessionProbe.app`，ad-hoc，
  TeamIdentifier=`not set`；codesign entitlement 读回无键值。
  二进制 SHA-256 `ab460bd57f126bf69526e42fda1fc0d4ce8946fc7cee6416c700ecf09e601408`。
- 当前 `application-identifier`：未包含；`keychain-access-groups`：未包含。
  所以不存在已核实的可用 application access group，不伪造当前 group 值。
- 原 SecItemAdd 为 session probe 的新唯一 service `G2C.CJAuth.session.<UUID>`、
  account=`synthetic-session-probe`；首次创建请求未传 access group，欲从成功返回
  属性取得自身默认组，但返回 **-34018 / errSecMissingEntitlement**，未到该步骤。
  随机 UUID 未写入成功 receipt，不能补造。未成功建项，后续读/删未执行。
- 唯一影响设备：CJ007-Session-20261021，iOS 17.5，
  `EAF9183B-2B0B-4D9C-BCB5-A9AA71C7BB01`；现已关机，应用已停止。
- 本轮只读签名证据：`../../evidence/message-key-signing-readback.txt`。
  未读旧 Keychain，没有重试已知失败的 SecItemAdd。

## 请求 Main 组织的一次最小确认

只为上述独占模拟器 probe，重新构建该 .app 并用 ad-hoc 签名应用旁边的
`CJ007Keychain.entitlements.plist` 两个精确键值：

| 键 | 当前 | 拟用（仅提案） |
|---|---|---|
| application-identifier | 缺失 | `CJ007SIM.local.g2c.cj007.sessionprobe` |
| keychain-access-groups | 缺失 | `["CJ007SIM.local.g2c.cj007.sessionprobe"]` |

拟用 prefix `CJ007SIM` 是**新提议的本地模拟器测试标识，不是已存在 Apple Team ID**。
不添加真实 team identifier、共享组、wildcard、iCloud、biometric 或其他能力。
系统是否接受该 ad-hoc 模拟器签名仍未验证；如仍失败，停止并报告，不自行增加键、
改 Apple 控制台、换其他 app 身份或复用用户项目配置。真机签名完全排除。

匹配约束：bundle ID 保持原值；拟 application-identifier 必须同时等于唯一
keychain-access-groups 元素及 adapter 的 applicationIdentifier 参数。任何一处
不匹配则不运行测试。library API 格式校验不等于签名归属验收。

## 新消息 key 的唯一预分配测试 scope

精确值在 `MessageKeyProbeScope.plist`，状态 PROPOSED_ONLY_NOT_APPLIED：
- environment=`6881AF7F-DB80-49E5-8EFD-740CAB24B304`
- account=`F50CD0D3-9621-46BB-B99D-7E2E7BED565F`
- purpose=`local-message-storage-v1`
- service=`G2C.CJAuth.message-key.6881AF7F-DB80-49E5-8EFD-740CAB24B304`
- Keychain account=`F50CD0D3-9621-46BB-B99D-7E2E7BED565F.local-message-storage-v1`
- access group=`CJ007SIM.local.g2c.cj007.sessionprobe`

这是只给本次 probe 的新 scope，不是产品默认环境/用户 ID。禁止更换 namespace
绕过未知 ACK 或清理失败。未在本轮查询或创建该项。

## 获得确认后才执行的步骤（当前全部 UNRUN）

1. 只运行包内 Probe/build.sh 重建 .app；它自身**不会**应用提案 entitlement。
   由获授执行者对该 .app 单次追加 ad-hoc 签名，使用旁边的精确 plist；读回签名、
   bundle ID、两个 entitlement、platform=IOSSIMULATOR，确认只涉及本任务产物。
2. 只启动上述设备，安装该 .app；不会注册根工程/正式能力，不接网络账号。
3. 三次独立进程启动，各次结束后停止应用：`--message-key-phase create`、
   `--message-key-phase restore`、`--message-key-phase clear`。
   前者生成新平台随机 key，存唯一 scope，Keychain 外只写 key ID 与合成密文；
   第二次读取原 ID 并解密固定合成消息；第三次先移除本任务合成密文再以精确
   expected key ID 删除，并验证原 scope 不再有项。日志/UI 不显示 key/session bytes。
4. 单独恢复 session probe 的三阶段仅在该最小确认同时覆盖时进行；当前已知失败
   不因这个文档自动重试。只删测试自己成功创建的精确项，不清整个 service/group。
5. 保存布尔结果/状态码/产物 hash，停止应用与本设备。任一 unknown/error 保留原
   scope/key ID，仅只读对账，不能新 key/新 scope 自动再跑或宣称清理成功。

## 风险、替代与范围

风险：签名产物会改变；系统可能仍拒绝模拟器 ad-hoc entitlement；测试项可能因
失败暂留，需要原 scope/ID 定向恢复。提案不获取真实账号/付费资源，也不改变用户
设备或其他应用安全设置。绝不把局部模拟器通过扩大为真机、共享组或生产验收。

替代方案：保持当前未应用状态，先交源码/iOS typecheck/注入测试；在后续已获准的
真实 G2C host target 中由 owner 提供正确签名/自身组，再跑同类安全测试。不能用
内存测试冒真实 Keychain PASS，也不能借旧 VP 组解决本依赖。
