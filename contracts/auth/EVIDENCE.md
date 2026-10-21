# CJ007 草案作者自测证据

2026-10-21，macOS 本地、Python 3.9.6；无网络/服务进程/安装/真实凭据。
候选范围：本文件所在提交的 `contracts/auth/**`；base
`00769d7f793566887a8e192a6ca7b35d8c5fb46a`。复现命令：
`python3 -B contracts/auth/check.py`。

- PASS：12 unittest 方法；其中 `test_server_examples` 执行 14 条 JSON
  服务端正负样例，其余方法覆盖客户端晚到/会话与提交前重查。
- PASS：正常自有资源、伪造 owner 不授予权限、嵌套外人引用/不存在资源拒绝、
  身份无效/未知、过期/撤销、资格拒绝/未知、旧产品环境拒绝。
- PASS：退出后响应、切号后响应及旧失效回调、同账号重登、进程重启、重复及
  乱序刷新、网络未知保留凭据、权威失效清除、资格独立、刷新不隐式切账号。
- 首次执行 FAIL：Python 3.9.6 求值 `tuple | None` 抛 TypeError。
  增加 postponed annotations 后同一命令 12/12 PASS；未更换解释器或降低断言。
- 合成限制：authority 是测试输入，不是验证器；resource owners 是假资源归属。
  `credentials_present` 不模拟真实安全存储；`deliver` 只模拟内存显示屏障。
  没有真实撤销、取消、持久化、后台运行、RLS、外部 SDK 或密码处理。
- UNRUN：独立 Review/Testing、真实新用户建号/验证/恢复、两个真实账号/API/DB
  隔离、SDK 刷新/后台恢复、安全存储删除失败、iOS/真机、CI、部署。
- PENDING：UI@1.0 与 AUTH 消费确认，正式登录与受邀策略、C2 环境和离线政策。
  草案未冻结、未发布 AUTH@1.0，不关闭 Issue #8。

内容变化后仅补受影响验证；正式 SDK/服务端/数据库实现必须另提供真实证据。
