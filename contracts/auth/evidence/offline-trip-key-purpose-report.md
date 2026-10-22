# Offline Trip snapshot 独立 key 用途 — 最小候选证据

实际 parent：f2c01d7e9e3292b7d8bcc207b965bf6a36cec96c，首写前 clean。
只读输入 CJ022固定24221d74e7d0ccb7f1d5afe27fa4384fc9c501ff 的
contracts/offline-trip/README.md；SHA-256：97061e359e8599607b58412ce3e2027ff7bd112174a82e154465c7db0e013318。
该契约要求独立于 localTripPendingV1 的 snapshot key，用途要求与本增量一致。

新增公开 MessageKeyPurpose.localOfflineTripSnapshotV1，raw value 固定
local-offline-trip-snapshot-v1。service 保持 G2C.CJAuth.message-key.<environment UUID>，
新 slot 为 <account UUID>.local-offline-trip-snapshot-v1。模块/provider/codec 不变；
Message/Memory/Trip/Needs/Feedback 全部原 raw value、service/slot 字节保持。

消费前先固定本增量并过原双审。可信 host 绑定 environment/account 与 backend 的
对应关系；本 namespace 没有另造 backend/trip 授权字段，不能根据不可信快照 metadata
换环境/账号取 key。CJ022必须比较期望 namespace、用途和认证 metadata 的原 keyID；
missing key 只意味着不可读，不能自动创建/轮换/迁移、改用 Trip pending key 或
session token。解密材料隔离不提供离线读授权、可信时间/rollback anchor、session
有效性或政策 TTL，CJ022 factory 仍保持关闭。

定向6/6 PASS（snapshot新3＋相邻Feedback3），见 offline-trip-key-purpose-tests.txt。
验证所有旧命名字节，六用途＋另一账号/环境八独立 key，跨 key 解密失败、错误
expectedID/operation拒绝、各旧用途清理后 snapshot key 保留、snapshot 清理后其他
scope保留，以及 unknown create/delete 原 key 只读对账（一次注入add/delete）。
仅CryptoKit合成字符串 roundtrip，不执行CJ022正式格式/codec或真实Trip验收。

生产源码仅新增一个enum case；其他变更仅定向测试/证据。未变生命周期/provider/
codec/typed-clear证据复用，不重跑所有套件/真实账号。没有SecItem、probe、signing、
权限、缓存或政策变更，无网络/生产配置/业务写入。原Keychain失败停机状态保持。
消费者须处理新增enum case并pin固定commit；此PASS不能提升离线平台/产品验收。
