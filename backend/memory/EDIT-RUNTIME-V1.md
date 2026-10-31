# CJ-MESSAGE-EDIT-MEMORY@1 — C adapter 冻结

#344；消费已冻结 B MESSAGE-send.4 / message-trip.2 与 EDIT-V1.md。
旧 local-memory-run.1/.2、message-trip.1 拒绝及所有旧接口不变。

## 显式本地配置

`cj_memory.edit_runtime.EditRuntimeConfiguration.from_bytes(raw)` 只接受新版本
`local-memory-edit-run.1`，恰为 version/collection/selections。collection 与 selections
完整复用原 local-memory-run.2 的 typed collection/明确人、slot、字节帽、期限验证；
不推断 slot、namespace 或 consent。最大262144 bytes，拒绝重复/多余字段和旧版本。
私有文件通过 load_edit_runtime_configuration 及原 read_private_policy 读取。

配置abi精确为 CJ-MESSAGE-EDIT-MEMORY@1，经可信组合放入
`EditConfiguration(memory=configuration,publisher=<实际C实现>)`。
bind 要求实际 canonical EditAuthority、相同 owner scope、fresh principal 与 scope/identity
匹配及有效显式政策；没有依赖、UNKNOWN 或不支持的配置不能产生空 Context。

## 原管道与短 source 租约

EditRuntimeMemory 继承原 typed runtime，复用 Service.consume_current_typed、
current_context/require_current、typed eligibility、整份 snapshot/epoch、编辑/启停/停止使用
fence、私有输出字节帽、原 RuntimeRun 与注册 Meter。共同 binder 在同包提取；旧 typed
入口的类型拒绝/行为不变。新捕获/hold 显式调用：

`authority.hold_for_effect(binding, source_lock=False)`

这先用 B 实际短检查取得当前来源，然后释放 Trip SHARE，才等 Memory 锁。
实际 namespace lease 的 check(binding) 通过后，仅把其 travel kind/id作为原ContextRef选择器；
版本、owner、Trip/消息/选区/namespace当前性由原 B 活 lease 核验，绝不以正式TripID替代。
namespace 数据、配置 ABI、DTO、相同 hash都不授使用/发布权限。

publication 已由 B 打开实际活 lease 时，reference_lease 复用该同authority/线程/生命周期
对象，不开第二个 Trip SHARE。Memory持有原scope锁和require_current至共同RUN提交，
C后续NEEDS fence/Trip UPDATE服从B原锁序。没有SQL lease跨model IO，没有第二引擎。

## 失败与兼容

捕获/期限/归属/当前性不明时保留 RuntimeDenied/RuntimeUnknown/原B异常语义，
withhold而非空Context/只保留长期/关闭Memory；临时source只来自实际独立travel namespace。
暂停/撤回的条目由原资格规则排除；这不是吞掉未知或未支持的有效记忆。
原结果/action/bytes/UNKNOWN对账、旧正式Trip不自动重写的规则保持。

实际C publisher由#336另交，C344测试桥只证明Memory消费与冻结发布接口组合，
不宣称#336/App/真实服务完成。不添加迁移、角色、权限、真实provider或费用。

验收包含实际签名API→受限私有PG→原worker/Fake、真实长期与两独立namespace临时条目、
编辑/暂停/恢复/停止使用/撤权及旧结果拒绝、unknown/错owner/失效namespace；
并发验证publication持Memory时capture不持Trip SHARE，及capture持Memory时Trip UPDATE可进、
publication等待后完成。旧profile拒绝和全部旧测试保留，完整回归/精确CI/独立红线另列证据。
