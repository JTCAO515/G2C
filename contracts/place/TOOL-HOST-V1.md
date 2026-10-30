# PLACE-TOOL-HOST@1 / MODEL-TOOL-TURN@1 — frozen

JT 2026-10-30 新版本/工具接入预授权下发布，owner B / #265。
只限 CJ_ENV=local、CJ-LOCAL-RUN@2、显式 synthetic-v1 tools profile 与 FakeProvider。
没有真实API、模型、key或费用许可；不存在的后台记忆生产者仍UNRUN，不由工具模拟。

## 原动作与唯一出口

正式 MESSAGE 接受后固定原 run；worker 在原 RUN fence/owner/currentness 检查下执行。
新注册表是代码持有 MappingProxy：model.tool_turn（kind=model）、tool.place（kind=tool），
继承原 MODEL_REGISTRY。参数只有冻结 PLACE-query.1；owner、scope、URI、key、budget、
attempt/period 等不能从模型控制。code-owned profile 不接受任意 Python/URL/transport。

每轮 model 的 operation_key 为 `model.tool_turn.<round>`；每个工具为
`tool.<round>.<index>`。原 args bytes 首次捕获后，PLACE-tool-input.1 包含原bytes的base64
和server派生request_ref，与原run/registration/kind/period/attempt一起由既有OperationStore
先持久，再经唯一 MeteredExitCore reserve/claim/final guard/clock/invoke/receipt。
request_ref 是原 run+逻辑位置的稳定派生关联，不是授权证明。

max_steps/max_tools/output/time 继续由原 Meter/Core 执行；不复制算法、放宽限额或重置
原period/UNKNOWN。callback不得注入许可；源准备和输入/请求构造在最后guard之前，实际
调用才增加producer计数。取消/撤权/失效后无新调用和晚到输出。运行中重启仍只核原
running→UNKNOWN，不自动重发；超时保留原claimed曝光，不按无结果/失败退款。

## 模型回合是数据

UTF8 JSON ≤65536 bytes，恰为 version=MODEL-tool-turn.1、kind、answer、calls。
kind=answer：answer恰为非空白zh/en文本，calls=[]。
kind=tool：answer=null，calls为1–16个 `{name,arguments}`，name必须存在代码注册表；
arguments只能是domain数据对象。重复/未知字段、非JSON数字和未知版本拒绝，不作为
plain text或默认允许执行回退。每次回合/工具都占原配置的限额，非法循环不能绕额度。

SyntheticToolModel 是明确标合成的本地模型：从合成中英提问产生typed请求，实际数据
由LocalPlaceProducer调用唯一prepare/parser后形成；不是用一个返回字符串的callback
代替业务producer。Data/source内容不修改工具注册、owner、预算或Trip确认权限。

## 输出与来源读回

用户可见 RUN text 保存JSONL：TOOL-output.1（data_origin=synthetic、name、operation_key、
result=PLACE-result.1）；TOOL-answer.1（data_origin=synthetic、text_zh/text_en）。
这是净化的typed资料，不含原HTTP body/credentials。真实供应商字节不进入本 profile。
无结果、限流、畸形、过期分别保留outcome并提示待核实；未知不标成功空页。

旧MESSAGE-send.1可沿原RUN读取；send.2用已冻结新RUN读版本携原reference。所有读取
仍核canonical owner/原binding；字段/label/hash不授予新步骤/发布或正式Trip接受。
实际A引用卡/App消费由#21/#266验证，本L1不冒称A完成。

启用 worker：`--tools-profile synthetic-v1` 或 CJ_LOCAL_TOOLS_PROFILE=synthetic-v1。
不配置则原model-only行为保持；@1计量配置不能启用tools。旧closed PLACE execute保持。
退出/回退时先停新producer，保留支持原operation/ref的consumer和历史账本；不重绑原动作。

验证：backend/cj_api/tests/place_tool_pg.py 使用新私有PG、签名本地app、正式worker/CLI，
实际model→PLACE→model调用>0、来源/路线读回、owner拒绝、原op稳定、限额/撤权/取消/
未知曝光；合成时钟不称物理过期，所有数据合成、不称录制。真实采集另停点授权。
