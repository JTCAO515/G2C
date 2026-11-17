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
`--first-setup`的old-chats文件必须为`{}`，不能带尚未经核定的旧目标。

每步C生成`NN-prepare.json`。A先完成只读UI准备：打开目标聊天/新聊天，按指示准备
未发送草稿，保留完整实际AX/截图。A写`NN-A-prepared.json`后，C才取**服务端原生
checkpoint**，再写`NN-admission.json`。A看到admission才执行该步发送/冷启动/
后台和锁屏返回/历史逐行打开，并写`NN-A-completed.json`。
准备期允许仅为选定目标打开历史及只读必要候选，不执行 SM03 正式全量巡检。
正式巡检和生命周期动作仍在 admission 后；准备期读取不能计作该步通过证据。

SM04在同一门禁下用两个`read_actions`：`background_return`、`lock_return`。
各有全计划唯一nonce和独立服务端checkpoint，分别使用`NN-1-*`、`NN-2-*`
两阶段文件；第一转场采集闭合才准入第二转场。每份witness只记录对应的一次
action/lifecycle快照。两个都PASS才计该语言SM04一个PASS；首FAIL/UNKNOWN即停，
不以同次转场的两个GET替代，不增加MESSAGE、模型调用或14项分母。

这样，准备时的旧GET不能替代真正恢复/返回后的读取。B以请求started/finished
exchange与服务端checkpoint前缀划步，不能以原件文件的迟发布时间划步。

A prepared格式`LIO-basic-app-prepared.2`含run_id、nonce、实际app、send_taps=0、
ui_before、artifacts。completed格式`LIO-basic-app-witness.2`的当前字段检查在
`joint_v2._ui/assess`：actual_ordinary_Home_AX、相同run/gate/locale/nonce/app、
独立观察的MID/CID均null，实际输入/单tap，before/after有序question/answer与草稿、
错误/完成状态，实际操作及逐次history/lifecycle产物。字段是接口约定，**不是已交
真实样件**；A尚不能观测的内容不手填或复制B ID凑数，缺证UNKNOWN。
transcript每行含question、answer（没有正文label时为null）、visible_failure布尔值，
可另保failure_label原AX文本。该布尔必须来自实际逐行UI，不从B状态复制；缺字段未知。
页面/会话/ACK/读取错误仍属global errors；checkpoint前已存在的原M若公开timeline
为failed并有quota/unavailable原失败，只允许如实匹配其正文/失败指示，不重新评成completed。
组合结果另列historical_public_failure_count。本轮新写入失败仍FAIL/STOP，原RUN和费用不改。
当前同源LioHome对failed行不显示正文，所以该行AX answer为null，即使原wire保留非空半句；
C只按实际展示分支投影，原answer与完整wire canonical仍保留，不把半句改写或标成成功。

冷启动/后台/锁屏必须保留本步唯一未发送草稿`SYNTH-DRAFT-<run>-<locale>-<gate>`。
standard的`old_chats[locale]`由实际App本地savedChats清单与B当前owner原M核对后
冻结：选中项含version=`LIO-readonly-history-anchor.1`、conversation_id、generation、
messages（每条message_id/run_id/sequence/canonical_sha256）；可附conversations数组，
包含同形全部App-local候选及与根字段一致的selected项。无数组时仅一个候选。
这些只读元数据不是正文、model claim或Memory权限；checkpoint返回分列的
history_targets，C再核原生CID/gen/完整有序M并从实际AppGET建立正文参考。
首次setup由真实seed逐步建立参考，不手填既有正文。App历史是该安装本地列表，
并非服务器全部CID；其他server-only记录保留在native_state，不冒称已删除或UI漏行。
固定默认`lio-original`行始终保留。B checkpoint另给`default_history_target`，
CID为当前身份原生`lio_conversation(scope)`；有正文时保留完整原M/代次，空对话
可messages=[]、generation=null。只有该实际默认目标允许空锚，普通旧聊仍须原M。
其实际`GET /v1/lio/timeline`无CID query，空page可conversation_id=null；原件以
origin=readonly_default、binding=null、实际default_conversation_id/default_generation
与当前身份/原生零M清单及完整GET exchange核对，不造MID、模型claim或费用。
非空默认读仍须真实MESSAGE binding，不能借空页规则免除原件。
SM03的history.default_row_key指完整实际AX列表末行；rows/opened同序逐行核，
由已核同源signed.history固定追加顺序关联默认角色，不能仅按标题猜，也不宣称
UI独立看见了CID。默认正文与其他行同文时，默认角色来自此实际顺序和点击原件。
真实timeline按20条分页。必须由同一步checkpoint后实际App GET的无cursor首页开始，
沿每个next_before匹配实际before请求，直到无下一页；页数/发布时间不能替代cursor链。
C仅在完整链有唯一内容且有序MID恰等当前原生全量清单时组合正文参考。页等价比较完整
wire对象的严格canonical字节（含卡片/来源/失败等字段），不能只比正文。缺首页/中页、
错cursor、循环、相同cursor的冲突完整内容仍UNKNOWN；相同完整页的重复poll可去重。
不同cursor的有效重叠页也必须对同一MID完整内容一致，不能只挑可连通链而忽略冲突页；
额外但一致的实际读页不要求删去。缺新MID的旧pre-accept poll不当最终内容。
accepted_conversations中的view_origin=actual_GET_cursor_chain和source_exchange_ids
标明它是C内部组合参考，version标记输入wire来源，不能将它当作某次原HTTP响应回传。
全部原页字节/摘要留在受保护读回中，准备期旧GET不能拼入，UI也须实际读全对应正文。
SM01须在冷启动恢复后、其他导航前立即留一个cold_launch lifecycle快照；如为
完整候选关联补读其他历史/默认项，后续成功不能修饰这张原快照的错误、草稿或正文。
历史每行都打开，完整有序问答在合法候选CID集合中必须恰一匹配。重名标题、行号、
通用能力正文或时间接近都不构成身份。需要远程读取的普通App路径须有该次真实
GET/完整原响应；A缓存正常加C另行读成功不能拼成PASS。当前实际normal Home
源码在scene active时调用refreshTimeline；如该行为改变须重新审实际路径。
每个history.opened项各保留errors/body_complete，不能用最后打开成功覆盖前一行
失败。新聊天写入还须有实际new_chat动作和发送前空transcript，原生新CID不替代
App真正切换到新聊天的证据。

## B原件与C判定

`programs.backend`指B实际签发、固定源码/配置的本机client入口，stdin为
`G2C-App-smoke-read-request.1`。C只传kind/locale/原nonce/plan/source/实际checkpoint_ref；
不传token。token由B已发的private client内存注入固定remote模块，不上传任意程序。

当前消费`G2C-App-smoke-host-read.1`的actual_roles与original。Native parser在
`native.py`核实际source/image/最小role/scoped census、原生before引用、实际新MID
集合、typed claim、raw HTTP outer/canonical摘要分列、去重前POST数及实际GET原件。
post_count=null、http_coverage UNKNOWN、gap、guard失败、timeout/nonzero不重试；
只有显式PENDING及精确`UNAVAILABLE/APP_SMOKE_HTTP_OUTER_PENDING`在同原
nonce/checkpoint/MID上有界等采集，不发新消息；后者仍须核实际host资格/source/
image/health，最终READ须通过全部身份、原件与费用检查。其他UNAVAILABLE即停。

原RUN正文与App timeline正文分别保留。用当前部署相同文件的
`cj_message.lio_context.display_answer(raw,locale)`核服务端已有投影，再将实际
timeline正文交A renderer核AX；不改写raw。host candidate的
`display_answer_source_sha256`必须来自B部署原文件，并与本地该模块文件SHA相同。

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
停新，其余UNRUN，结果写#1048。`real_gate_status`仅表示该候选基础链路；
`release_allowed=false`、`jt_invitation_status=UNRUN`始终保留，脚本不签发发布或
JT邀请。只有另行核实目标构建/发行产物及所需App证据、真实全PASS后才能写#702。
CLI退出0仅表示real_gate_status=PASS；FAIL/UNKNOWN/UNRUN退出1，与发布许可分开。

注入测试callback的执行始终标L0_CONTROL、real_gate_status=UNRUN、release_allowed=false。
本地fixture的14个逻辑PASS不能生成真实发布证书。23:00–08:00不开始UI准备/新请求；
原件核对使用原授权、原ID，不能借fresh Memory种子恢复已收回用途。
