# Feedback pending 独立密钥用途 — 668 后置增量

实际 parent：668d96b8e22227160991e2416dc547dacf12246b，首写前 clean。
新增 `MessageKeyPurpose.localFeedbackPendingV1 = "local-feedback-pending-v1"`。
模块仍为 CJMessageKeys，provider/记录编码/生命周期不变。

service 保持 `G2C.CJAuth.message-key.<environment UUID>`，Feedback 独立 slot 为
`<account UUID>.local-feedback-pending-v1`。Message/Memory/Trip/Needs 四个原用途的
raw value、service/slot 字节不变，不迁移/复制/轮换旧 key，不新增权限或 raw-key 构造。

候选客户端必须用可信 host 的环境/账号和该 purpose 选择 provider，获取后核
key.namespace 与原 expected key ID；pending metadata 只能比较，不可选择另一 scope。
未知不能当 missing，也不能新建 key 绕过原 ciphertext/receipt；复用原创建与清理
只读对账机制。创建/清理仍须消费方确认密文条件，不能用销毁 key 代替原 action
query/receipt hash 核对。Session token 或其他用途 key 均不能作 fallback。

定向6/6 PASS（Feedback新3＋Needs原3），日志
[evidence/feedback-key-purpose-tests.txt](evidence/feedback-key-purpose-tests.txt)。
覆盖旧字节、五用途/另一账号/另一环境七独立 key、错 key 解密/expected ID/operation
拒绝、每个旧用途清理不影响 Feedback、Feedback 清理不影响其他 scope，以及
unknown 创建/清理只读恢复原 key，各一次实际注入 add/delete。

只用了注入 persistence、平台随机与 CryptoKit 合成数据；无真实 SecItem、签名/
probe、网络或账号动作。其余未改生命周期证据复用，原668 Needs与4718 typed-clear
门禁独立保持，本次 PASS 不替代它们的验收。未改 Package/root/backend/client、
provider、访问组或默认业务入口；新增用途不授权真实 Feedback POST。

消费者须 pin 此后置 fixed commit，并处理 enum 新 case；候选客户端原 bytes 文件
持久化、业务回执/恢复与真实平台仍由原 owner 验证，不宣称此 key 用途即完成产品。
