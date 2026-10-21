# CJ-SESSION-STORE@0.1.0-rc.1 — host 生命周期接口候选

base f3c8e5074eb27de0de6fef6dd7558763cbcf4291，独立 product CJSession。
本轮只改 CJAuth 包；后端/JWT 固定成果不动。接口尚待 CJ006/CJ009 消费确认。

SessionNamespace(environment: UUID, slot: String) 必须由 host 为新 G2C 环境分配，
没有旧 VP/service/access-group fallback。SessionMaterial 只接可信 SDK host 给出的
opaque session bytes，不收密码，不 Codable、不进偏好/日志，文本/Mirror 脱敏。

SessionLifecycle(persistence:, restorePolicy: .userInitiatedOnly) 提供：
- beginTrustedSDKSave → save(material, for: 原操作)；beginUserRestore → load(for: 原操作)。
- 操作绑定实例、身份代次和原操作/用途，仅一次可消费；host await 后必须 isCurrent
  再使用恢复结果/写 UI，不用当前新操作给旧 SDK 回调重标。
- clear 先使旧操作失效，再清凭据；load/save/clear 异常均显式返回并阻本生命周期
  继续恢复/保存。clear 重试成功才解除本地阻断，旧代次永不恢复。
- noteNetworkUnknown 不碰存储或身份代次。读取成功只是 loadedNeedsVerification，
  不是已登录/已受邀；canUseRestrictedBusiness 恒 false。
- 自动恢复接口始终不可用；这是本候选的显式有限能力，不是已接受的最终 UX。
  重启后也不会自动读取凭据。真正自动恢复策略及 SDK/host 接线仍需后续确认。

一个 namespace 只允许一个 host 生命周期 writer；本包不声称多进程/多 coordinator
原子性。首次进入新账号流程前 host 必须 clear，并同步清 CJShell 私有内容。真实 SDK
会话刷新/账号识别、安全输入、服务端验证和邀请资格均独立，不能由本地 store 授权。
