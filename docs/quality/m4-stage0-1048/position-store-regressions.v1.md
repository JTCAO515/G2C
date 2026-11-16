# #1048：位置持久化附加回归 / Position persistence regressions

这三项补充 UI01 的本机恢复边界，不重写原25条、后续27条索引或任何冻结用例。
不并入基础14项、全国16条、模拟用户60条或正式66例的分母。只使用合成数据和
A 的独立临时目录/既有夹具；不改 JT 的安装、账号、密钥、journal 或授权目录。

These three cases extend local recovery coverage. They do not change any existing
cohort or denominator. Use A's isolated synthetic fixtures, never JT's installation,
account, keys or journal. No real provider, HTTP, Trip or Memory action is needed.

## 来源与证据 / Source and evidence

- 原缺陷：[PR1089 独立审查](https://github.com/JTCAO515/G2C/pull/1089#issuecomment-6915297106)，
  head `fb48d52722b37848c83ac41642e6beaaae253f77`。丢稿为 P1；重复键和 FIFO 阻塞各为 P2。
- A 的返修候选回执：`dab1e45ce6d8da5bfbaa9d735d28af52f2fa8566`，并非本文声称已合并或部署的版本。
  A 报告 Shell314/Lio140/store11 及中英浅深局部原生夹具通过；C 未独立重跑这些 Swift/UI 检查。
- Original defects were independently reproduced on the pinned old head. Candidate
  fixture results are A's report, not actual BetaRoot, Hong Kong, device or release evidence.
  **本文交付状态：场景已定义；候选独立复验及真实范围均 UNRUN。** 原 FAIL 保留，不标“已修复”。

## POS01：未入 journal 的首问与后续草稿并存 / Unstaged first question plus another draft

**输入 / Input**

- 中文：首问 A 为 `  北京三日游\n `，保留夹具原 ID 和中文语言标记；A 尚未 staged 到 SDK journal。
  输入框另有非空、未发送的 B：`  再看看上海，先别发送。\n `。
- English: A is `  Plan three days in Beijing.\n ` with its original fixture ID and English language;
  it has not been staged. The composer contains a different unsent B: `  Maybe Shanghai instead; do not send yet.\n `.
- 通过实际 signed-library 夹具编码、冷恢复，再调用实际 library.restore；不要通过真的发出
  UNKNOWN 来造前置。随后仅在该本机夹具中让 B 的正常 accepted 路径完成，再核 A。
  Here `\n` denotes an actual newline in fixture data. Do not replace original UTF-8 or trim spaces.

**期望与判定 / Expected and judgement**

A 的原 ID、原 UTF-8 和语言全部可恢复；B 的原 UTF-8 不被覆盖。逐个检查恢复期间的持久
checkpoint，不能只检查最后一次状态；后续 B accepted 后 A 仍在。恢复本身 POST=0、lookup=0，
不自动重发、不换 ID，不生成另一个旧动作。成本/未知动作与真实会话授权不由这个夹具证明。

Both A and B survive every durable checkpoint. A keeps its original ID, exact bytes and language,
including after the fixture accepts B. Recovery performs no POST or lookup and invents no resend.

本机入口：`LioChatContinuityTests.coldUnstagedFirstAndDifferentFollowupDraftBothRemainDurable`，
位于 `ios/Modules/CJShell/Tests/CJLioUserTests/LioChatContinuityTests.swift`。

## POS02：重复格式字段不能选择恢复版本 / Duplicate format cannot select a version

**输入 / Input**

用夹具的合法位置编码生成 format=1 原文，分别在前面和末尾加入另一个 format=99，保留两种
字段顺序。当前可见草稿分别为 `保留当前草稿` / `Keep the visible draft`。如测试持久层，使用
A 的合法作用域加密夹具封装这段歧义明文；直接破坏密文只能测试 AEAD，不能证明重复键被拒。

Create both duplicate-key orders from a valid format=1 record with another format=99. Wrap plaintext
with the existing scoped encryption fixture when testing storage; ciphertext corruption is a different case.

**期望与判定 / Expected and judgement**

两种顺序都以 `RecoveryError.invalidSnapshot` 拒绝；当前草稿/位置原样保留，不任选一个版本，
不按 format1 重写或把坏记录当空状态。保留失败输入及两次结果；不新增 JSON 解析实现。

Reject both orders, preserve current state and the invalid original, and do not rewrite it as a valid version.

本机入口：`LioChatPositionTests.duplicateVersionCannotChooseWhichPositionToRestore`，
位于 `ios/Modules/CJShell/Tests/CJLioUserTests/LioChatPositionTests.swift`。

## POS03：位置路径为 FIFO 时不能等待 writer / FIFO must not block on a writer

**输入 / Input**

仅在 A 夹具新建的私有临时目录，将固定位置文件名创建为0600 FIFO，分别使用中文/英文夹具
标签；不创建或修改真实 App 文件。调用原 store.load。沿既有夹具保留延迟 writer 的红例，
避免把“后来有 writer 才返回”误记为非阻塞通过。

In A's fresh private fixture directory only, place a 0600 FIFO at the fixed position filename, using
Chinese and English fixture labels. Exercise the actual store, retaining the delayed-writer counterexample.

**期望与判定 / Expected and judgement**

以 `RecoveryError.unsafeDirectory` 拒绝，且拒绝不依赖 writer 出现；保留 fstat/no-follow/single-link
边界。旧 R 探针的313.6ms阻塞是 FAIL。沿 A 的既有本机非阻塞断言，不把它设为真实启动时延门槛；
不能改目标文件、覆盖现有记录或降级为空白恢复。无 writer 时也不得无限等待。

Reject without waiting for a writer, preserve the file and existing state, and retain the original safety
checks. The local probe's timing is not a new product launch SLA or real-service result.

本机入口：`LioChatPositionStoreTests.nonRegularPositionIsRejectedWithoutWaitingForAWriter`，
位于 `ios/App/Acceptance/LioChatPositionStoreTests.swift`；复用 A 的 App-owned store harness。

## 复跑与分层 / Replay and evidence layers

在对应 PR1089 候选的隔离树中，模块入口沿原命令：
`swift test --package-path ios/Modules/CJShell --filter 'LioChatPositionTests|LioChatContinuityTests'`。
App store harness 与局部 UI 由 A 原入口执行；不要因文件尚未在 main 就自行复制或伪造状态。
记录精确 source、运行 ID、每个反例、原日志及首次失败，本文不代替命令实跑。

真实 Beta/HK 如需扩展 POS01，必须另核前置、原动作/费用、独占窗口和夜间限制；不得挤入基础
14项报价，也不通过忽略 STOP_NEW 来准备。缺实际 producer、原件、候选或窗口时记 UNRUN/UNKNOWN。
