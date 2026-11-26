# 案件字段揭示规则

[#1712 Part 1](https://github.com/JTCAO515/G2C/issues/1712) 提供 playbook 后端规则。演练数据默认显示 `masked_value(field_name)` 的类型化占位符。普通页面和队列渲染无需读取原值。

| 固定 playbook 版本和当前步骤 | 白名单字段 |
| --- | --- |
| `p0_assistance/1/verify_assistance` | 联系电话、会合地点 |
| `document_loss/1/verify_document_situation` | 旅客名字 |

其他步骤的白名单为空。护照号码保留占位符。值班处理员只能为当前分配给自己的案件申请。

## 申请与读值

工作台从已验证会话与案件分配构造 `RevealActor`。在现有工作台权限、案件所有权与 CSRF 边界内调用后端，申请和每次读值都重新核对角色与分配。浏览器只提交字段、理由选项及后续的授权 ID。

- `RevealWorkflow.request(case_id, actor=..., field_name=..., reason=...)` 返回申请审计与可用授权。申请必须提交理由选项 `locate_traveler`（寻找或联系旅客）或 `verify_lost_document_report`（核对遗失情形）。授权绑定案件、员工、字段、步骤、案件修订号和 5 分钟截止时间。申请接口只返回授权元数据。
- `RevealWorkflow.reveal(case_id, actor=..., grant_id=..., lookup=...)` 返回审计与可选值。读取时复查当前案件和白名单，并在返回前确认有效期。授权在到期、案件关闭或修订变更时失效。值只在合规读取时由服务端的合成查询函数取得。
- `RevealAudit` 包含操作、时间、人员、案件、步骤、字段、理由选项和结果。事件不含授权 ID、原值或自由输入。Part 2 将每次申请和读值的返回审计追加到工作台审计存储，并在审计写入成功后返回揭示值。

工作台应在一次服务端操作中持有现有案件分配锁，保证检查的是当前分配。后端在同一案件工作流锁内读取、校验并取得合成值，避免并发关闭或推进跨过校验。授权只存本地进程内存，进程重启后需重新申请。上线页面与审计落存由 JT2 接续。
