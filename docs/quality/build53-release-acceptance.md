# 构建 53 发布后验收清单

对应 [#1368](https://github.com/JTCAO515/G2C/issues/1368)。按 [JT 决定](https://github.com/JTCAO515/G2C/issues/495#issuecomment-7096832261)，构建 52 跳过。本清单继承 [#1341 执行单](https://github.com/JTCAO515/G2C/issues/1341#issuecomment-7095462192) 和 [52 原判据](build52-release-acceptance.md)，并覆盖 53 的十二项新功能。

## 执行顺序与证据

1. S 发布前按 #1368 跑快速冒烟，记录香港实际 source/image、上线时间和已开关的插件。开通且获授权的新插件各做一次真实查询。A 在 #702 公布 TestFlight 53 内部分发及三处同源说明。完整验收与全国规划实测独立于发布，按各自资格执行。
2. 先模拟器核入口和界面，再验实际 TestFlight 53。顺序为基础链路、千问翻译、使馆搜索、滴滴、隐藏项、已发布的新功能。每版按 A 的发布说明验当次新功能。A 留精确 App 提交、分发构建、设备/iOS、语言、默认字号及去敏界面证据。S 提供匹配的真实终态、原服务回执和计量。短码登录与各插件开通只报获批人数及计数。
3. 中英、浅深色、系统默认字号核入口、无结果、错误状态和无障碍标签。供应商独立中转、名单限制、配额、署名和敏感字段范围以合入的授权为准。外部依赖未齐的插件须隐藏，验入口并记原因，具体能力记 UNRUN。酒店和火车票入口均隐藏。购买和预订只验官方落地，不下单或付款。
4. 每格记录时间和时区、操作、预期、可见结果、同轮证据及 PASS／FAIL／UNKNOWN／UNRUN。已跑且关键证据未能核同记 UNKNOWN；明确不符记 FAIL；尚未跑记 UNRUN。模拟器、夹具、真实香港、真机分别留证。同轮原件只在受限位置核查，GitHub 只留去敏摘要。

## 原 52 执行单并入 53

基础七项中英文各一轮。使用同一项在模拟器与真机分别留证；第 05–07 项各从新对话开始。凡涉及回复，单独核可见正文、原 RUN 和费用。

| 项 | 怎么测 | 看什么证据 | PASS |
| --- | --- | --- | --- |
| 01 启动恢复 | 旧对话留草稿，强退重开 | A 的前后界面和时间，S 的原 CID、timeline 与 MESSAGE 差值 | 同一对话、原消息、草稿恢复，零新增发送。 |
| 02 新建问答 | 新对话问北京是不是中国首都 | A 可见答案，S 新旧 CID、MID/RUN、原正文和计量 | 新 CID 独立，答案正确、完整、与提问同语。 |
| 03 历史 | 从历史分别开旧对话和第 02 项的对话 | A 历史列表及两次进入画面，S 两个 CID 和原 timeline | 两个对话均可打开，各自原消息正确。 |
| 04 后台／锁屏 | 留草稿，后台 10 秒返回，再锁屏 60 秒返回 | A 两次时点及界面，S 对应 CID 原读和 MESSAGE/attempt 差值 | 两次都恢复原对话和草稿，零重复发送和开场白。 |
| 05 身份 | 问「你是谁」／“Who are you?” | A 可见正文，S 同轮 MID/RUN、原文和计量 | 用提问语言说明 Lio 身份，有实际正文。 |
| 06 能力 | 问「你能做啥」／“What can you do?” | A 可见正文，S 同轮 MID/RUN、原文和计量 | 用提问语言给具体可用能力；只有引文、标题或否认能规划均不通过。 |
| 07 规划 | 问「北京三日游」／“Plan three days in Beijing” | A 正文或日卡，S 原 MID/RUN、计量；若报保存，查同动作 Trip、版本和回执 | 北京三天每天至少有两个带地名的可执行活动，具备时段或先后顺序。裸地点、空卡、截断不通过；无日期预览零正式保存，自称已保存须有原件。 |

| 项 | 怎么测 | 看什么证据 | PASS |
| --- | --- | --- | --- |
| MT01 文字 | 中→英、英→中各提交一条示例文本，复制译文并试现役朗读入口 | A 输入、译文、复制和朗读记录；S 的同轮香港中转、千问成功终态及原计量 | 正确可见译文，复制和朗读按实际开通路径可用；来源标注与回执一致。仅走联网翻译。 |
| MT02 语音 | 真机麦克风中英各说一句，结束录音 | A 听写、译文和操作时点；S 原 ASR、MT 终态及计量 | 听写与译文均正确。502、只到 ASR INTENT、未进入翻译均不通过。[语音回归](m4-stage0-1048/release-regressions.v1.md#2026-11-23--千问中英语音-502) |
| MT03 拍照 | 真机拍中英文示例文字各一份 | A 原图、识别结果、译文；S 图像请求原终态、来源、计量 | 实际拍摄后两方向译文对应原图。相册和夹具只作补充。 |
| LA01 使馆搜索 | 中英界面各搜两个国籍，每种界面至少一次用英文国名；各试一次无匹配 | A 的发布 PR、随包版本、查询到详情的结果及对应外交部目录 | 命中逐一对上名称、地址、电话；无匹配有明确提示。字段或来源未核清记 UNKNOWN，只查看号码。 |
| TX01 行程地点 | 从行程活动打开打车，选起点，核预填终点，打开滴滴 | A 选点、预填与落地页；S 同次 TAXI.1 原链接回执及坐标来源 | 选点、预填和落地对应，确认页即停，零订单。 |
| TX02 手动输入 | 插件手动选不同起终点，估价后打开链接，分别验已装／未装滴滴 | A 估价界面和两种落地页；S 同轮估价回执、`price_display` 与链接回执 | 价格原样，起终点一致；未装可走网页，确认页即停，零订单与付款。 |
| 隐藏项 | 在实际构建的中英插件页和已知入口尝试进入 | A 发布说明、插件列表、开关和入口证据 | 酒店、火车票及因依赖不足未发布的插件不可见、不可从其他入口进入。 |

## 53 十二项新功能

| 项 | 怎么测 | 看什么证据 | PASS |
| --- | --- | --- | --- |
| N01 附近 [#1362](https://github.com/JTCAO515/G2C/issues/1362) | 真机验首次同意／拒绝定位、手动地点和行程选点，切美食、景点、咖啡、购物和 500 米、1 公里、3 公里，试综合和距离排序；在北京、成都各查一次各分类；开详情依次测打车、导航、中地址卡、问 Lio、加进行程 | A 权限、带归属高德图、列表、五个动作及确认结果；S 坐标转换、周边原字段、缓存、额度、名单负例与计量 | 隐私同意后才加载地图，拒绝仍能手动选。地图与列表同一地点；距离、评分、人均、营业、照片只显示回执支持的值，补译有标记。导航/打车目标一致，加行程走现有确认和写入守卫。 |
| N02 本地协助 v2 [#1256–#1261](https://github.com/JTCAO515/G2C/issues/1251) | 用示例资料逐测求助草稿、Lio 紧急引导、总领馆领区选择、给当地人看的中文卡、我在哪及医疗卡的查看和清理 | A 各入口、离线卡片、权限、退出／清理证据和实际总领馆来源；S 的联动回执或获准逆地理编码元数据 | 引导到正确入口，领区与权威来源相符，拒绝定位或无网提示明确，地址来源可核。样例卡片按确认的存储、显示、清理规则工作。真实求助发送等 JT 指定接收渠道；本轮只验输入。 |
| N03 图片原位翻译 [#1373](https://github.com/JTCAO515/G2C/issues/1373) | 拍照与相册各给多行示例，交换中英语种，切原图、覆盖和逐行视图；用批准的本地夹具核空块和越界 | A 同图截图、坐标对齐及无结果状态；S 的 qwen-mt-image 真实终态、坐标契约和计量 | 译文覆盖对应文字位置，不越界、不错行；逐行一致，空结果可辨。相册入口和夹具不代替真机拍照成功。 |
| N04 千问朗读 [#1374](https://github.com/JTCAO515/G2C/issues/1374) | 从译文、常用语各播中英文示例，试停止、超时、同句重播 | A 可听音频与停止、错误状态；S 千问 TTS 成功回执、额度，重播计量差值 | 读出对应文本和语言，可停止；失败后有明确状态。同一缓存句重播零新增供应商派发。 |
| N05 汇率换算 [#1372](https://github.com/JTCAO515/G2C/issues/1372) | 用小数金额测人民币与常用币种双向换算，含最近参考日、节假日或刷新失败 | A 双向结果、ECB 数据日、来源和参考提示；S 同日 ECB 原值及缓存状态 | 用同日 EUR 基准交叉计算，先算后显示舍入。无新发布时显示实际参考日；失败不显示伪造汇率。 [ECB 官方参考汇率](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) |
| N06 地铁指南 [#1370](https://github.com/JTCAO515/G2C/issues/1370) | 中英逐城切北京、上海、成都，核买票、进出站、安检、线路图链接 | A 实装逐条文案、路线入口落地页和核对日；下节官方逐项基准 | 各城说明和官方对应，外卡/乘车码适用范围明确，能打开该城运营方或主管部门线路图。 |
| N07 常用语卡片 [#1369](https://github.com/JTCAO515/G2C/issues/1369) | 逐句核点菜、问路、打车、购物、就医；各类选一句全屏，再返回和朗读 | A 中英文、出处、大字显示、返回位置及可听记录；S 按 N04 绑定音频 | 语义相符，中文可直接出示，返回原列表；朗读对上所选句子。就医内容限沟通语句。 |
| N08 支付开通指南 [#1371](https://github.com/JTCAO515/G2C/issues/1371) | 中英逐步看支付宝／微信支付的注册、绑境外卡、验证和常见失败，再从 App 打开官方入口 | A 实装步骤和去敏样图、官方落地页、平台出处及核对日 | 两套步骤与官方对应，卡种、验证、失败处理注明适用条件。页面只展示说明，零绑卡、零转账或测试付款。 |
| N09 航班 [#1364](https://github.com/JTCAO515/G2C/issues/1364) | 国内、国际各一，用航班号及起讫地与日期两种查；加我的航班，手动刷新，核行程和机场交通入口 | A 查找、详情、手动刷新、联动界面；S 飞常准同轮字段、时间/状态及额度 | 航班号、日期和计划/实际起降不串，延误/取消及登机口等只显示真实有值字段，缺值有状态；行程跳转绑定正确航班。 |
| N10 天气 [#1365](https://github.com/JTCAO515/G2C/issues/1365) | 查北京、成都、上海，验定位允许／拒绝改选城，切当前、24 小时、7 天、两小时降水、预警和建议，核行程日期 | A 中英、和风署名、选城、预警及行程界面；S 源字段、地时、缓存与额度 | 数据对应城市、时区与发布时间；预警与无预警可区分，源缺字段不编值；行程映射日期正确。 |
| N11 上网卡 [#1366](https://github.com/JTCAO515/G2C/issues/1366) | 看中国大陆、香港、澳门及多地套餐和按天数推荐，开官方购买页；逐步读中英安装说明 | A 套餐、推荐理由、Airalo 落地、安装图文和来源；S 同轮目录原字段、价格/币种/有效期 | 覆盖与套餐真实对应，购买页正确，零下单；热点、实名、漫游、激活按具体套餐，缺字段明确。 |
| N12 玩乐 [#1367](https://github.com/JTCAO515/G2C/issues/1367) | 查北京、成都和景点关键词，切排序，核详情、行程明细和官方预订跳转 | A 列表、详情、行程动作、Klook 落地；S 同轮搜索与详情、价格/币种、日期及取消政策 | 列表与详情同产品，价格、日期、取消和集合点与原回执一致；已授权行程写入守卫生效；官方落地零订单、零付款。 |

N09–N12 的凭据和相应供应商授权状态见 [#1368 等 JT 清单](https://github.com/JTCAO515/G2C/issues/1368#issuecomment-7096959065)。已合入的 [M4 条目 13](../authorizations/M4.md) 是 ECB，不作为四家供应商的调用授权。按实际开通状态验收。

## 资料类逐条核对

下表记录 2026-11-23 核到的官方基准。最终稿以 A 发布 PR 和实际构建为输入，逐条补「构建、条目或界面、来源与日期、结果」。未交付的稿件和无法访问的入口保持未验证。出现差异到对应票贴出处、预期和实装位置。

| 内容 | 逐条核对基准 |
| --- | --- |
| 北京购票、进出站 | 对照实体单程票、支持方式的外卡拍闸和已开通的乘车码。区分购票支付和直接刷闸。[北京地铁乘车规定](https://www.bjsubway.com/support/ccgd/) · [北京市政府乘地铁指南](https://english.beijing.gov.cn/travellinginbeijing/transportation/beijingsubway/202512/t20251229_4374803.html) |
| 北京安检、线网 | 进站接受安检；线路图从运营方当前「线路图查询」入口核，不引用旧快照。[北京安检](https://english.beijing.gov.cn/specials/beijinglifeonthesubway/noticeforpassengers/202206/t20220623_2749395.html) · [北京地铁官网](https://www.bjsubway.com/) |
| 上海购票、进出站 | 机器购买单程票；外卡购票、拍闸、乘车码分别写，并按线网适用范围与车站标识核。[上海政府乘地铁指南](https://english.shanghai.gov.cn/en-Individuals-Transportation-PublicTransport/20260813/f257d5c373db4da3a8bde717b9f46b27.html) |
| 上海安检、线网 | 安检是进站常规步骤。上海运营方线路图本次抓取超时，待 A 附构建内可打开的官方落地及版本，现记 UNKNOWN。[上海安检](https://english.shanghai.gov.cn/en-FAQs-TravelinShanghai/20240531/c328df3c38054bdcb66160007eb85b4f.html) · [运营服务入口](https://service.shmetro.com/) |
| 成都购票、进出站 | 买单程票及外卡拍闸按商务部访客指引和站点标识核。若文案列乘车码或具体线路的例外，要求该城市自己的出处。[商务部 2026 指引，乘坐交通工具](https://www.mofcom.gov.cn/ztxx/art/2026/art_90fd4865144d4ddab192742bf386bbd1.html) |
| 成都安检、线网 | 进站按要求接受安全检查。成都运营方线网入口本次抓取超时，待 A 附构建内实际打开的官方页面，现记 UNKNOWN。[国务院条例](https://www.gov.cn/gongbao/2024/issue_11686/material/gwygb202431.pdf) · [成都轨道集团线网入口](https://www.chengdurail.com/index/jtxwt.htm) |
| 支付宝 | 下载／注册、添加符合条件的境外卡和验证为独立步骤，确认卡种和截图与当前平台一致。[上海政府支付指南](https://english.shanghai.gov.cn/en-Individuals-BankingandPayments-Payments/20260920/4fc94c2f0e6b47e7939969415e5feb04.html) |
| 微信支付 | 用境外手机号注册或登录、在钱包添加符合条件的境外卡。验证按平台提示，常见拒绝分发卡行拒绝和平台验证。[腾讯访客指南](https://www.tencent.com/zh-cn/tencent-further-enhances-digital-payment-services-for-visitors-to-china-with-process-streamlined-and-more-overseas-wallets-linked/) · [商务部 2026 指引，开通移动支付](https://www.mofcom.gov.cn/ztxx/art/2026/art_90fd4865144d4ddab192742bf386bbd1.html) |
| eSIM 兼容、安装 | 先查机型、销售地区与运营商锁，保持联网，按套餐提供的 QR 码或官方流程添加 eSIM。[Apple 旅行 eSIM](https://support.apple.com/en-us/118227) · [Airalo iOS 安装](https://www.airalo.com/help/getting-started-with-airalo/E8DFWD88SHUX/5001/3Z7U0CAC64GF) |
| eSIM 数据、激活、覆盖 | 选该 eSIM 为蜂窝数据线，漫游和 APN 按套餐说明。有效期以实际套餐条款为准。中国覆盖范围的说明只适用于相应 Airalo 套餐及其移动数据，不能推广为任意境外 eSIM。[Airalo iOS 设置](https://www.airalo.com/help/getting-started-with-airalo/E8DFWD88SHUX/5001/3Z7U0CAC64GF) · [Airalo 中国覆盖说明](https://www.airalo.com/help/using-managing-esims/ZSEEHBT5HW6F/stay-connected-in-china-your-guide-to-unfiltered-internet-access-is-a-vpn-required/ZDZBNIKI4TFP) |
| 点菜、问路、购物、就医 | 分类逐句检查表达对象和语义。对照「想看菜单」「怎么走」「多少钱」「需要去医院」等同类表达，未在参照中出现的句子要求自己的来源。[港科大（广州）生活指南](https://studyathkustgz.hkust-gz.edu.cn/uploadfile/2025/02/26/17-12-11/Revised_Life%20in%20Guangzhou.pdf) |
| 打车 | 区分目的地、行驶方向和停车要求，逐句核译义；地点以示例文本展示。[西交利物浦大学生存中文](https://www.xjtlu.edu.cn/wp-content/uploads/2022/10/2022_International_Student_Welcome_Guide.pdf) |

已把资料口径交功能票 [地铁](https://github.com/JTCAO515/G2C/issues/1370#issuecomment-7096959156)、[常用语](https://github.com/JTCAO515/G2C/issues/1369#issuecomment-7096960459)、[支付](https://github.com/JTCAO515/G2C/issues/1371#issuecomment-7096960007)、[eSIM](https://github.com/JTCAO515/G2C/issues/1366#issuecomment-7096959601)。

## 全国规划与结果归档

- 按 [#994](https://github.com/JTCAO515/G2C/issues/994) 原口径验基础 8 条，同源 8/8 且正式归还后，S 在 [#815](https://github.com/JTCAO515/G2C/issues/815) 签发 ACTIVE。换批前绑定实际 source/image、原账和冻结输入／判据，新批使用新 ID。旧批结果和费用保留。
- 每批 S 的规划修复上线后，在一个有效窗口按冻结顺序串行跑完整 16 条。明确语义 FAIL 后继续；UNKNOWN、服务端错误或触及保守费用上限停发。单轮 ≤¥100 且以原 C 余额为上限。目标 ≥12/16。每轮在 #815 一次交 S 全部可证失败、未跑项、原因与原费用。
- 53 真机结果回 [#1368](https://github.com/JTCAO515/G2C/issues/1368)，先给结论再链接逐项证据。去敏后用原反馈模板建立与 #1368 关联的子票，按现象给 A 或 S。每个已证实故障回填 [发版回归集](m4-stage0-1048/release-regressions.v1.md)，沿用原判据。Q 只处理 JT 转交后的脱敏反馈，状态原地更新 [#759](https://github.com/JTCAO515/G2C/issues/759#issuecomment-7094909212)。
