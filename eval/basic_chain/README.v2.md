# #1048 基础冒烟执行 v2

本版接 B 的真实受保护原件，A 的普通 Home UI 测试/真机产物。旧设计、plan.1、
observation.1、cost.1及旧审查/失败保留；新版计划为plan.2，新执行入口为host.2。
当前仍是**本地实现/控制测试，真实14项UNRUN**；不是已部署、已获ACTIVE或已可邀请JT。

## 调用数量与金额分别约束

Source审计固定在949ea369的National/RealTools路径。固定身份/能力中英四条零外呼；
其余每条最多intake1+普通8回合+Memory1，工具共8（包括城市解析，不能另加第九）。

| 用途 | 消息 | 模型上界 | 总工具上界（含免费） | 现金目的上限 | 窗口 |
|---|---:|---:|---:|---:|---:|
| standard | 8 | 40 | 32 | ¥60 | ≤60分钟 |
| first_setup | 12 | 80 | 64 | ¥80 | ≤90分钟 |

见`execution-profiles.2.json`。原C100、原usage/hold、native800/400及其他线不增加。
B原生begin逐次检查原全额hold；现金和调用上界同时独立约束。72/144只是把调用
包络都按1元粗加，既不是同时占用/预付款，也不是紧的实际费用或发票上限。
本上限不保证整个cohort一定跑完；预算拒绝即资源受限UNKNOWN/停新、剩余UNRUN，
不冒称L产品故障，也不改loop/env或补额来掩失败。需新增资金先问JT。

只有实际装配、源码分支和所有生产者已核定时可沿此quote开窗；actor/reflection或
额外后台模型不在此包络。Native4/无日期正式保存有独立资格，不能借本版预览通过。

## 一个C命令与A两阶段产物

```sh
uv run --locked python -B -m eval.basic_chain prepare \
  --app "$ACTUAL_APP_PIN" --old-chats "$OLD_CHATS" --first-setup --output "$NEW_PLAN"
uv run --locked python -B -m eval.basic_chain run --execute \
  --plan "$NEW_PLAN" --host "$ACTUAL_HOST_CONFIG" --output-directory "$NEW_PRIVATE_RUN"
```

`prepare`不联网。目录须不存在，产物0700/0600，不覆盖旧阶段。两个A自有隔离
simulator可以分别绑定C中英身份；实际UI为L1、香港为L2，不能写成真机L3或同一发行IPA。

每步C生成`NN-prepare.json`。A先完成只读UI准备：打开目标聊天/新聊天，按指示准备
未发送草稿，保留完整实际AX/截图。A写`NN-A-prepared.json`后，C才取**服务端原生
checkpoint**，再写`NN-admission.json`。A看到admission才执行该步发送/冷启动/
后台和锁屏返回/历史逐行打开，并写`NN-A-completed.json`。

这样，准备时的旧GET不能替代真正恢复/返回后的读取。B以请求started/finished
exchange与服务端checkpoint前缀划步，不能以原件文件的迟发布时间划步。

A prepared格式`LIO-basic-app-prepared.2`含run_id、nonce、实际app、send_taps=0、
ui_before、artifacts。completed格式`LIO-basic-app-witness.2`的当前字段检查在
`joint_v2._ui/assess`：actual_ordinary_Home_AX、相同run/gate/locale/nonce/app、
独立观察的MID/CID均null，实际输入/单tap，before/after有序question/answer与草稿、
错误/完成状态，实际操作及逐次history/lifecycle产物。字段是接口约定，**不是已交
真实样件**；A尚不能观测的内容不手填或复制B ID凑数，缺证UNKNOWN。

冷启动/后台/锁屏必须保留本步唯一未发送草稿`SYNTH-DRAFT-<run>-<locale>-<gate>`。
历史每行都打开，完整有序问答在合法候选CID集合中必须恰一匹配。重名标题、行号、
通用能力正文或时间接近都不构成身份。需要远程读取的普通App路径须有该次真实
GET/完整原响应；A缓存正常加C另行读成功不能拼成PASS。当前实际normal Home
源码在scene active时调用refreshTimeline；如该行为改变须重新审实际路径。

## B原件与C判定

`programs.backend`指B实际签发、固定源码/配置的本机client入口，stdin为
`G2C-App-smoke-read-request.1`。C只传kind/locale/原nonce/plan/source/实际checkpoint_ref；
不传token。token由B已发的private client内存注入固定remote模块，不上传任意程序。

当前消费`G2C-App-smoke-host-read.1`的actual_roles与original。Native parser在
`native.py`核实际source/image/最小role/scoped census、原生before引用、实际新MID
集合、typed claim、raw HTTP outer/canonical摘要分列、去重前POST数及实际GET原件。
post_count=null、http_coverage UNKNOWN、gap、guard失败、timeout/nonzero不重试；
只有显式PENDING在同原ID/checkpoint上等采集，不发新消息。

`programs.projector`是A提供的同源只读render出口。输入
`LIO-reply-projection-request.1`含app/raw_utf8/input_sha256；输出
`LIO-reply-projection.1`含app、renderer_source_sha256、input_sha256、rejected、
rendered_utf8/rendered_sha256。普通完成态必须是
`String(LioReplyMarkdown.render(raw)!.characters)`，与真实最终lio.answer AX逐字核对。
source、Foundation环境和实际AX均须核实；不能任意折叠空白、二次解析或按TextBlock重拼。
仅有纯函数向量不等于实际显示成功。

Host配置版本`LIO-basic-chain-host.2`含实际app（surface、renderer_source_sha256）、
candidate（source/image/schema/qualification_sha256/policy_sha256/tool_implementation_sha256）、
subjects、native_ledger_id、pricing、B实际purpose_receipt的path/SHA、三个采集时间界限，
以及经核准的backend/projector入口path/SHA/qualification_ref。配置不授原生权限。
实际B包、实际A候选与采集器未交齐前不组装伪资格。

## 费用与结果

`cost_v2.py`保留cost.1，新增明确分层：真实登记工具的原响应/RECEIVED/Meter结算/
来源与owner/attempt均核实、全部前后台生产者与账覆盖闭合、原hold完整保留时，
**未知价格不等于未知动作**。district仍保原place满1元，token估计/实付UNKNOWN；
不当免费。固定NIA公开抓取/local visitor免费必须有各自正向源及原回执，不能将缺
收费原件泛化为0。未知注册、INTENT、未结算、模型identity/DONE/usage无效、擦除/
权限拒绝、原件或全覆盖缺失仍UNKNOWN。模型计费元数据不签发模型payload或工具
结果被后续模型使用的三段链证书；后者保留#32原门槛。

每项保留三栏费用/已知小计、实际时间、source与UI ID为空的真实来源说明。总额只在
全部原账覆盖完整且不重复时相加；缺实付发票不填0。14项固定分母，首FAIL/UNKNOWN
停新，其余UNRUN，结果写#1048；只有同候选真实全PASS才可#702邀请JT。

注入测试callback的执行始终标L0_CONTROL、real_gate_status=UNRUN、release_allowed=false。
本地fixture的14个逻辑PASS不能生成真实发布证书。23:00–08:00不开始UI准备/新请求；
原件核对使用原授权、原ID，不能借fresh Memory种子恢复已收回用途。
