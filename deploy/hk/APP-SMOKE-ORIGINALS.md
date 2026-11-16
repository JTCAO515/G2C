# 普通 App HTTP 与动态原件（B-only）

本切片承接 App smoke claim，尚不等于已安装的香港窗口或十四项 PASS。
普通1/2不保存完整 outer；这里在真实 HTTP 边界另采原字节，不能从 canonical JSON 重建。

## API 观察器

`api --app-smoke-api-manifest <0600文件>` 仅在固定C两主体和冻结输入的资格内启用。
API策略为 `G2C-App-smoke-outer-window.1`：policy_path / policy_sha256 指向原worker策略，
directory及device/inode指向独立UID10001/0700的outer目录。它不是worker的model/Memory
artifact或rejected-intakes目录；API不因此得到这些原件的读取权。

POST仅观察现有/v1或/v2/lio/messages，原请求仍由正常App/原API处理；不发第二份POST。
元数据started/finished日志记录实际HTTP交换，先于MESSAGE幂等去重，不能用一个claim
推断只收了一次POST。正文上界沿现有16384字节；只保留固定输入的普通App UUID。
未授权主体、登录路由、query/认证字段不进入原文采集。

一个队列线程最多保留12个请求，不新建Runtime。它等待真正worker claim和return，
再用原RuntimeOriginals的当前AUTH/MESSAGE边界核原绑定与两种摘要，发布0600原文及receipt。
原HTTP响应和异常不改写。缺claim、失败最终检查、过期或队列溢出只会缺证/UNKNOWN，
不重发、不重建bytes，不因稍后读成功改旧UNKNOWN capture receipt。

GET仅观察同资格下实际App的/v1或/v2/lio/timeline及/v2/lio/messages查询。
只认已登记且闭合原件的CID/MID；未知旧对话不放宽为通配，首次可由真实seed4闭合。
保存实际选择器和完整response body（≤256KiB），当前AUTH/原M-frame通过后才有capture receipt。
未完成body、超限、未知选择器或缺receipt不能拼成恢复PASS。
纯本地历史列举不虚构远程API。A旧缓存加B另一次GET也不能代替实际App读请求。

## 同源受保护批量读口

`python -B -m deploy.hk.app_smoke_read <B的API策略路径>` 从stdin接既有token，
不在argv、日志或输出回传token。原请求G2C-App-smoke-read-request.1绑定expected_source、
plan_sha256、冻结step nonce。checkpoint在服务端以O_EXCL写owner/plan/nonce绑定原生状态、
唯一账本行集和HTTP基线；observe只认这份原件的checkpoint_ref，不接受client自带before。

- 原控制claim必须在当前M历史边界与genuine receipt的scope/MID/CID/generation/RUN/sequence、
  canonical SHA核同。outer SHA来自原worker读取的native outer摘要，HTTP原bytes与其独立比对。
- 费用逐原operation读取原Meter和financial row，包含失败/UNKNOWN；local visitor事实须无付费原行。
  C行账本增量必须精确等于本步原金融attempt集合，旧行必须不变。
- producer-return仅是一项必需原件；还核ACK、关联Memory history已闭合和前后台状态。
  新/变更后台来源目前保持UNKNOWN，不能用空队列/前台completed推全覆盖或填零。
- saved Memory摘要只含非candidate current items；新抽取job不冒已保存偏好写入。
  所有检查使用实际最小运行角色，字段缺失/原权限失效按UNKNOWN，保留subtotal和原hold。
- actual HTTP读原件与去重前POST计数另列；UI独立MID/CID可为空，不把B原件复制成App独立观测。
  实际A UI产物、单步单writer、完整候选CID集合与正常renderer投影仍由A/C联合核验。

prepare模块仅生成新的本机0700/0600 PREPARED_NOT_ACTIVE包，不联网、不分配MID、不开户/加钱。
本机路径和inode不能直接当香港资格；B须在真实主机按现有流程装配、核实源像/角色/原账/全部在途，
独审固定helper与包后再签实际新lease。候选没有全部十四项真实PASS之前不通知JT重试。
