# 候选资料索引（2026-11-18 批次）

本文件是本批**候选**资料的维护索引。所有条目状态均为 `待核实`，不是已确认事实，不得直接进入 Lio 回答、FACT wire 或页面事实库；格式、边界与晋级流程见 [README.md](README.md)。

- 批次日期：2026-11-18
- 候选总数：**99** 条（城市/场馆 75 + 工具 24）
- 文件数：8 个 JSON + 本索引 + [缺口与冲突记录](2026-11-18-gaps-and-conflicts.md)
- 城市键：19 个（含 `nationwide`）；主题（城市/场馆）13 个；工具类别 8 个
- 来源类型（城市/场馆批次）：政府 35 条、场馆/景区官方 26 条、交通运营方 8 条、商业平台 3 条、其他公开来源 2 条、官方媒体/政府新闻 1 条；工具批次另计（官方应用商店 9、政府 5、工具官方 3、商业平台 3、运营方 2、官方媒体 2）
- 有来源发布日期的条目：城市/场馆 33 条、工具 8 条；来源标注有效期/截止日的条目：3 条
- 与其他候选共用同一来源 URL 的条目：9 条（城市/场馆批次，可能重复，待查重）
- 记录到明显冲突的条目：城市/场馆 17 条、工具 6 条；`missing` 为空的条目：0 条

## 文件与分组

| 文件 | 分组说明 | 条数 |
|---|---|---|
| [2026-11-18-first-time-basics.json](2026-11-18-first-time-basics.json) | 首次来华基础（支付、上网、抵达、铁路、住宿登记、退税、求助渠道） | 14 |
| [2026-11-18-south-cities.json](2026-11-18-south-cities.json) | 华南与东南城市景点（广州、深圳、桂林、厦门） | 12 |
| [2026-11-18-east-cities.json](2026-11-18-east-cities.json) | 华东城市景点（南京、苏州、上海） | 11 |
| [2026-11-18-central-west-cities.json](2026-11-18-central-west-cities.json) | 中西部城市景点（武汉、长沙、成都、西安、重庆） | 12 |
| [2026-11-18-north-other-cities.json](2026-11-18-north-other-cities.json) | 北方及其他热门城市景点（北京、青岛、哈尔滨、昆明、张家界、洛阳） | 12 |
| [2026-11-18-planning-and-channels.json](2026-11-18-planning-and-channels.json) | 行程规划与官方渠道（节假日、无障碍、亲子、季节、签证入境渠道） | 12 |
| [2026-11-18-visa-entry-channels.json](2026-11-18-visa-entry-channels.json) | 人工补充的官方渠道与住宿登记（国家移民管理局） | 2 |
| [2026-11-18-tools.json](tools/2026-11-18-tools.json) | 常用 App 与工具（`visitor-tool.1`；支付、地图、城市交通、打车、铁路、翻译、预订、通信） | 24 |

## 城市覆盖

| 城市键 | 城市 | 条数 | 涉及主题 |
|---|---|---|---|
| `nationwide` | 全国 | 18 | 抵达与住宿登记、紧急求助、亲子、上网/手机卡、支付、铁路/高铁、节假日与季节、城市与城际交通、行程规划、签证入境官方渠道 |
| `beijing` | 北京 | 8 | 无障碍、抵达与住宿登记、景点参观、护照预约与购票、铁路/高铁、节假日与季节、城市与城际交通、行程规划 |
| `shanghai` | 上海 | 7 | 无障碍、抵达与住宿登记、景点参观、亲子、护照预约与购票、支付、铁路/高铁、节假日与季节、城市与城际交通、行程规划 |
| `guangzhou` | 广州 | 6 | 无障碍、抵达与住宿登记、景点参观、亲子、铁路/高铁、城市与城际交通 |
| `chengdu` | 成都 | 4 | 抵达与住宿登记、景点参观、护照预约与购票、铁路/高铁、城市与城际交通、行程规划 |
| `wuhan` | 武汉 | 3 | 景点参观、护照预约与购票 |
| `xian` | 西安 | 3 | 景点参观、护照预约与购票、节假日与季节 |
| `nanjing` | 南京 | 3 | 景点参观、亲子、护照预约与购票、节假日与季节、行程规划 |
| `suzhou-jiangsu` | 苏州（江苏） | 3 | 无障碍、景点参观、亲子、护照预约与购票、行程规划 |
| `shenzhen` | 深圳 | 3 | 无障碍、景点参观、亲子、城市与城际交通 |
| `guilin` | 桂林 | 3 | 景点参观、护照预约与购票、城市与城际交通 |
| `xiamen` | 厦门 | 3 | 抵达与住宿登记、景点参观、亲子、护照预约与购票、城市与城际交通、行程规划 |
| `changsha` | 长沙 | 2 | 景点参观、护照预约与购票 |
| `luoyang` | 洛阳 | 2 | 景点参观、节假日与季节、城市与城际交通、行程规划 |
| `qingdao` | 青岛 | 2 | 景点参观、亲子、节假日与季节、行程规划 |
| `kunming` | 昆明 | 2 | 景点参观、节假日与季节、城市与城际交通、行程规划 |
| `chongqing` | 重庆 | 1 | 景点参观、护照预约与购票 |
| `harbin` | 哈尔滨 | 1 | 景点参观、亲子、节假日与季节、城市与城际交通、行程规划 |
| `zhangjiajie` | 张家界 | 1 | 景点参观、城市与城际交通、行程规划 |

## 主题覆盖

| 主题键 | 主题 | 条数 | 涉及城市 |
|---|---|---|---|
| `attraction` | 景点参观 | 45 | 北京、长沙、成都、重庆、广州、桂林、哈尔滨、昆明 等 |
| `trip_planning` | 行程规划 | 20 | 北京、成都、哈尔滨、昆明、洛阳、南京、全国、青岛 等 |
| `transport` | 城市与城际交通 | 20 | 北京、成都、广州、桂林、哈尔滨、昆明、洛阳、全国 等 |
| `passport_booking` | 护照预约与购票 | 14 | 北京、长沙、成都、重庆、桂林、南京、上海、苏州（江苏） 等 |
| `seasonal_holiday` | 节假日与季节 | 13 | 北京、哈尔滨、昆明、洛阳、南京、全国、青岛、上海 等 |
| `family` | 亲子 | 12 | 广州、哈尔滨、南京、全国、青岛、上海、深圳、苏州（江苏） 等 |
| `arrival` | 抵达与住宿登记 | 9 | 北京、成都、广州、全国、上海、厦门 |
| `accessibility` | 无障碍 | 7 | 北京、广州、上海、深圳、苏州（江苏） |
| `rail` | 铁路/高铁 | 7 | 北京、成都、广州、全国、上海 |
| `visa_entry` | 签证入境官方渠道 | 5 | 全国 |
| `payment` | 支付 | 4 | 全国、上海 |
| `internet` | 上网/手机卡 | 1 | 全国 |
| `emergency` | 紧急求助 | 1 | 全国 |

## 工具与 App 批次（`visitor-tool.1`）

文件：[2026-11-18-tools.json](tools/2026-11-18-tools.json)，24 条；逐条说明见 [2026-11-18-tools.md](tools/2026-11-18-tools.md)。类别：城市公共交通 10、支付 3、通信 3、地图 2、翻译 2、预订 2、打车 1、铁路 1。范围：全国 14 条；城市特定 10 条（北京、上海、广州、深圳、成都、西安、杭州、重庆、南京、武汉）。

- 地方工具中 7 条 App Store 标注简体中文和英文，3 条仅简体中文（渝畅行、与宁同行、Metro 新时代）；全国工具的界面语言按来源页标注，部分英文界面待核实。
- 4 条官方英文名未找到，按 `name_en=未知` 记录：亿通行、渝畅行、与宁同行、Metro 新时代。
- 6 条记录到冲突或口径差异：百度地图、滴滴、Trip.com、Airalo、亿通行、Metro 大都会。
- 全部 24 条 `missing` 非空，均未做安装、注册、绑卡、购票或乘车实测。

| id | 名称（中/英） | 类别 | 范围 | 界面语言 | 官方入口 | 主要来源 |
|---|---|---|---|---|---|---|
| `tool.2026-11-18.alipay` | 支付宝（Alipay） | 支付 | 全国 | 中文、英文界面待核实、其他语言未知 | [支付宝官网](https://www.alipay.com/) | [上海市人民政府英文网站《A guide to linking international bank cards to Alipay》](https://english.shanghai.gov.cn/en-FAQs-StudyinShanghai/20231211/a58d4c15179f468fb2c5d72b393f1fd4.html) |
| `tool.2026-11-18.wechat` | 微信（WeChat） | 支付 | 全国 | 中文、英文（官方英文站；App 界面语种待核实） | [WeChat 英文官网](https://www.wechat.com/en) | [微信支付帮助中心《微信支付外卡绑定和使用指南》](https://cs.help.wechat.com/hc/zh-cn/articles/11975770896271-%E5%BE%AE%E4%BF%A1%E6%94%AF%E4%BB%98%E5%A4%96%E5%8D%A1%E7%BB%91%E5%AE%9A%E5%92%8C%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97) |
| `tool.2026-11-18.cloud-quickpass` | 云闪付（Cloud QuickPass） | 支付 | 全国 | 英文、简体中文、繁体中文、韩文、日文、维吾尔文、藏文 | [云闪付官网（中国银联）](https://www.95516.com/) | [济南市投资促进局转载《开通移动支付（外国商务人士在华工作生活指引 2025 年版）》](http://zwfw.jinan.gov.cn/col127495/art/2025/art_127495_4798604.html) |
| `tool.2026-11-18.amap` | 高德地图（Amap） | 地图与导航 | 全国 | 中文、英文、西班牙语、葡萄牙语、法语、德语、泰语、日语、韩语、土耳其语、意大利语、俄语、阿拉伯语、马来语、印尼语、越南语 | [高德地图官网](https://www.amap.com/) | [上海市人民政府英文网站《China's first multilingual map adds 14 new languages》](https://english.shanghai.gov.cn/en-Latest-WhatsNew/20250711/8f2fcf3c6b624a56a6b2c0d8152ea2f2.html) |
| `tool.2026-11-18.baidu-maps` | 百度地图 / Beijing Map 英文版（Baidu Maps / Beijing Map） | 地图与导航 | 全国 | 英文（Beijing Map）、中文（百度地图主站/主 App）、其他语言未知 | [Beijing Map 英文地图](https://web.beijingmap.cn/) | [北京市人民政府英文网站 Beijing Service《Beijing Map》](https://english.beijing.gov.cn/specials/beijingservice/pek/baidumap/) |
| `tool.2026-11-18.didi-china` | 滴滴出行（DiDi China） | 打车 | 全国 | 英文、中文（界面）；其他语言待核实 | [DiDi 国际官网](https://web.didiglobal.com/) | [Google Play《DiDi China: Ride Hailing》应用页](https://play.google.com/store/apps/details?id=com.sdu.didi.psnger) |
| `tool.2026-11-18.rail-12306` | 中国铁路 12306（China Railway 12306） | 铁路/高铁 | 全国 | 中文、英文（英文网站）；App 界面语种待核实 | [中国铁路 12306 英文站](https://www.12306.cn/en/index.html) | [中国铁路 12306 英文版常见问题（Ticketing）](https://www.12306.cn/en/faq.html) |
| `tool.2026-11-18.pleco` | Pleco 汉语词典（Pleco Chinese Dictionary） | 翻译 | 全国 | 英文（界面与释义）、中文（词典内容）、粤语发音 | [Pleco 官网](https://www.pleco.com/) | [Pleco 官网](https://www.pleco.com/) |
| `tool.2026-11-18.microsoft-translator` | 微软翻译（Microsoft Translator） | 翻译 | 全国 | 60 多种语言（应用商店说明）、界面支持多语言（具体语种待核实） | [Microsoft Translator 官网](https://www.microsoft.com/en-us/translator/) | [Microsoft Translator 官网](https://www.microsoft.com/en-us/translator/) |
| `tool.2026-11-18.trip-com` | 携程国际版（Trip.com） | 预订 | 全国 | 24 种语言（App Store 说明） | [Trip.com 官网](https://www.trip.com/) | [Trip.com 官网](https://www.trip.com/) |
| `tool.2026-11-18.booking-com` | 缤客（Booking.com） | 预订 | 全国 | 英语及另外 40 种语言（App Store 说明，含简体/繁体中文） | [Booking.com 官网](https://www.booking.com/) | [Booking.com 官网](https://www.booking.com/) |
| `tool.2026-11-18.china-unicom` | 中国联通（China Unicom） | 通信上网 | 全国 | 中文；英文服务待核实 | [中国联通官网](https://www.10010.com/) | [中国政府网（China Daily 呈现）《How can foreigners apply for a SIM card...》](https://govt.chinadaily.com.cn/s/202508/15/WS689ed552498edec913ce0dc8/how-can-foreigners-apply-for-a-sim-card-and-choose-a-suitable-mobile-communication-service-plan-in-china.html) |
| `tool.2026-11-18.china-mobile` | 中国移动（China Mobile） | 通信上网 | 全国 | 中文；英文服务待核实 | [中国移动官网](https://www.10086.cn/) | [中国政府网（China Daily 呈现）《How can foreigners apply for a SIM card...》](https://govt.chinadaily.com.cn/s/202508/15/WS689ed552498edec913ce0dc8/how-can-foreigners-apply-for-a-sim-card-and-choose-a-suitable-mobile-communication-service-plan-in-china.html) |
| `tool.2026-11-18.airalo` | Airalo 中国 eSIM（Airalo China eSIM） | 通信上网 | 全国 | 英文；其他语言见网站语言选择（未逐项核实） | [Airalo 中国 eSIM](https://www.airalo.com/china-esim) | [Airalo 中国 eSIM 页面](https://www.airalo.com/china-esim) |
| `tool.2026-11-18.beijing-yitongxing` | 亿通行（英文名未知） | 城市公共交通 | 北京 | 简体中文、英文 | [App Store 亿通行](https://apps.apple.com/cn/app/id1247890676) | [App Store《亿通行》页面](https://apps.apple.com/cn/app/id1247890676) |
| `tool.2026-11-18.shanghai-metro-daduhui` | Metro 大都会（Metro Daduhui） | 城市公共交通 | 上海 | 简体中文、英文 | [App Store Metro 大都会](https://apps.apple.com/cn/app/id1202750238) | [上海市人民政府英文网站《CIIE service guide: Easy metro access》](https://english.shanghai.gov.cn/en-CIIE2025/20251017/c6c5ca124ee74e92a37244280c0983b9.html) |
| `tool.2026-11-18.guangzhou-metro` | 广州地铁官方 APP（Guangzhou Metro） | 城市公共交通 | 广州 | 简体中文、英文 | [App Store 广州地铁官方 APP](https://apps.apple.com/cn/app/id580097761) | [App Store《广州地铁官方APP》页面](https://apps.apple.com/cn/app/id580097761) |
| `tool.2026-11-18.shenzhen-metro` | 深圳地铁-官方 APP（Shenzhen Metro） | 城市公共交通 | 深圳 | 简体中文、英文 | [App Store 深圳地铁-官方 APP](https://apps.apple.com/cn/app/id848926994) | [深圳地铁官网《运营服务·常见问题》](https://www.szmc.net/shentieyunying/yunyingfuwu/changjianwenti/) |
| `tool.2026-11-18.chengdu-metro` | 成都地铁-官方 APP（Chengdu Metro） | 城市公共交通 | 成都 | 简体中文、英文 | [App Store 成都地铁-官方 APP](https://apps.apple.com/cn/app/id1303414976) | [App Store《成都地铁-官方APP》页面](https://apps.apple.com/cn/app/id1303414976) |
| `tool.2026-11-18.xian-metro` | 西安地铁-官方 App（Xi'an Metro） | 城市公共交通 | 西安 | 简体中文、英文 | [App Store 西安地铁-官方 App](https://apps.apple.com/cn/app/id1325483350) | [App Store《西安地铁-官方App》页面](https://apps.apple.com/cn/app/id1325483350) |
| `tool.2026-11-18.hangzhou-metro` | 杭州地铁-官方 APP（Hangzhou Metro） | 城市公共交通 | 杭州 | 简体中文、英文 | [App Store 杭州地铁-官方 APP](https://apps.apple.com/cn/app/id1131121104) | [App Store《杭州地铁-官方APP》页面](https://apps.apple.com/cn/app/id1131121104) |
| `tool.2026-11-18.chongqing-yuchangxing` | 渝畅行（英文名未知） | 城市公共交通 | 重庆 | 简体中文 | [App Store 渝畅行](https://apps.apple.com/cn/app/id1491110313) | [App Store《渝畅行》页面](https://apps.apple.com/cn/app/id1491110313) |
| `tool.2026-11-18.nanjing-yuning-tongxing` | 与宁同行（英文名未知） | 城市公共交通 | 南京 | 简体中文 | [App Store 与宁同行](https://apps.apple.com/cn/app/id1600886078) | [App Store《与宁同行》页面](https://apps.apple.com/cn/app/id1600886078) |
| `tool.2026-11-18.wuhan-metro-new-era` | Metro 新时代（英文名未知） | 城市公共交通 | 武汉 | 简体中文 | [App Store Metro 新时代](https://apps.apple.com/cn/app/id1121139634) | [App Store《Metro新时代》页面](https://apps.apple.com/cn/app/id1121139634) |

## 中西部城市景点（武汉、长沙、成都、西安、重庆）

文件：[2026-11-18-central-west-cities.json](2026-11-18-central-west-cities.json)，12 条。

| id | 标题 | 城市 | 主题 | 来源（名称 / 域名） | 来源类型 |
|---|---|---|---|---|---|
| `candidate.2026-11-18.wuhan.yellow-crane-tower-park` | 黄鹤楼公园门票政策、开放时间与优免人群（官网） | 武汉 | 景点参观 | [中国黄鹤楼公园官方网站（武汉市黄鹤楼公园管理处）](http://www.cnhhl.com/index.php/list-12.html) / `www.cnhhl.com` | 场馆/景区官方 |
| `candidate.2026-11-18.wuhan.hubei-provincial-museum` | 湖北省博物馆个人预约须知：开闭馆时间与预约渠道 | 武汉 | 景点参观、护照预约与购票 | [湖北省博物馆官方票务预约平台（预约须知页）](https://pcticket.hbww.org.cn/) / `pcticket.hbww.org.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.wuhan.east-lake-scenic-area` | 武汉东湖风景区多片区免费开放（市政府门户报道） | 武汉 | 景点参观 | [武汉市人民政府门户网站（来源：长江日报）](https://www.wuhan.gov.cn/sy/whyw/202310/t20231025_2286295.shtml) / `www.wuhan.gov.cn` | 政府 |
| `candidate.2026-11-18.changsha.hunan-museum` | 湖南博物院开放时间、免费陈列与实名预约规则（官网） | 长沙 | 景点参观、护照预约与购票 | [湖南博物院官网（参观信息）](https://www.hnmuseum.com/zh-hans) / `www.hnmuseum.com` | 场馆/景区官方 |
| `candidate.2026-11-18.changsha.yuelu-mountain-orange-isle-scenic-area` | 岳麓山·橘子洲旅游区实名预约与放号规则（区政府网站转载） | 长沙 | 景点参观、护照预约与购票 | [长沙市岳麓区人民政府网站（来源：湘江早报）](http://www.yuelu.gov.cn/jdhy/1473506/qt/202310/t20231007_11241187.html) / `www.yuelu.gov.cn` | 政府 |
| `candidate.2026-11-18.chengdu.chengdu-wuhou-shrine-museum` | 成都武侯祠博物馆2026年延时开放与线上预约通告 | 成都 | 景点参观 | [成都武侯祠博物馆官网公告](https://whpwm.cdwuhouci.cn/announcement/69) / `whpwm.cdwuhouci.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.chengdu.jinsha-site-museum` | 成都金沙遗址博物馆因综合提升闭馆（2025-12-05至2027-04-30） | 成都 | 景点参观、行程规划 | [成都金沙遗址博物馆官网（首页开馆时间）](https://www.jinshasitemuseum.com/) / `www.jinshasitemuseum.com` | 场馆/景区官方 |
| `candidate.2026-11-18.chengdu.dujiangyan-scenic-area` | 都江堰景区购票须知：开放时间、实名制与外籍游客入园方式 | 成都 | 景点参观、护照预约与购票 | [都江堰旅游门户网（购票须知页）](https://www.djy517.com/online.html?channelCode=mpyd) / `www.djy517.com` | 其他公开来源 |
| `candidate.2026-11-18.xian.huaqing-palace-huaqing-pool-mount-li` | 华清宫（华清池·骊山）开放时间与官方购票渠道 | 西安 | 景点参观、节假日与季节 | [陕西华清宫官方网站（游玩攻略）](https://www.hqc.cn/Play/Raiders/) / `www.hqc.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.xian.xian-city-wall-scenic-area` | 西安城墙景区开放时间与最大承载量（景区网站） | 西安 | 景点参观 | [西安城墙景区网站（在线商城页）](http://www.chinaxiancitywall.com/product.php) / `www.chinaxiancitywall.com` | 场馆/景区官方 |
| `candidate.2026-11-18.xian.shaanxi-history-museum-main-branch` | 陕西历史博物馆2026年冬季开放时间（官网公告） | 西安 | 景点参观、护照预约与购票 | [陕西历史博物馆官网（参观公告）](https://www.sxhm.com/guide/visit/detail/3018590.html) / `www.sxhm.com` | 场馆/景区官方 |
| `candidate.2026-11-18.chongqing.dazu-rock-carvings-scenic-area` | 大足石刻景区分时预约、承载量与“五一”假期开闭园安排 | 重庆 | 景点参观、护照预约与购票 | [大足石刻研究院官网（公示公告）](http://www.dzskyjy.cn/web/article/1461299413116395520/web/content_1461299413116395520.html) / `www.dzskyjy.cn` | 场馆/景区官方 |

## 华东城市景点（南京、苏州、上海）

文件：[2026-11-18-east-cities.json](2026-11-18-east-cities.json)，11 条。

| id | 标题 | 城市 | 主题 | 来源（名称 / 域名） | 来源类型 |
|---|---|---|---|---|---|
| `candidate.2026-11-18.nanjing.sun-yat-sen-mausoleum-zhongshan-scenic-area` | 南京中山陵陵寝：实行实名预约参观，陵门以上区域8:30-17:00、墓室不开放 | 南京 | 景点参观、护照预约与购票、行程规划 | [南京市中山陵园管理局网站《让我看看是谁还没放假~》](https://zschina.nanjing.gov.cn/lyzx/202606/t20260618_5862979.html) / `zschina.nanjing.gov.cn` | 政府 |
| `candidate.2026-11-18.nanjing.ming-xiaoling-mausoleum` | 南京明孝陵景区：售票时间6:30-18:30，纳入钟山风景区实名预约购票 | 南京 | 景点参观、护照预约与购票、亲子 | [南京市中山陵园管理局网站《让我看看是谁还没放假~》](https://zschina.nanjing.gov.cn/lyzx/202606/t20260618_5862979.html) / `zschina.nanjing.gov.cn` | 政府 |
| `candidate.2026-11-18.nanjing.nanjing-museum` | 南京博物院：秋假延时至11月18日20:00，11月19日起恢复9:00-17:00并需全员实名分时段预约 | 南京 | 景点参观、护照预约与购票、节假日与季节 | [搜狐号“江南时报社”《秋假期间，南京博物院延时开放》](https://www.sohu.com/a/1102256752_120596020) / `www.sohu.com` | 商业平台 |
| `candidate.2026-11-18.suzhou-jiangsu.suzhou-museum-main-branch` | 苏州博物馆本馆：周二至周日9:00-17:00、周一闭馆，实名分时段预约 | 苏州（江苏） | 景点参观、护照预约与购票、无障碍、亲子 | [苏州博物馆官网《开放指南》](https://dx.szmuseum.com/views/NewsDetails.aspx?guid=8303b714-0945-4600-86df-65bef4391835) / `dx.szmuseum.com` | 场馆/景区官方 |
| `candidate.2026-11-18.suzhou-jiangsu.humble-administrators-garden-zhuozheng-garden` | 苏州拙政园：3-10月7:30-17:30、11月至次年2月7:30-17:00，闭园前停止售票/入园 | 苏州（江苏） | 景点参观、行程规划 | [苏州市旅游咨询中心（苏州市文化广电和旅游局主管）景区介绍页《拙政园》](https://visitsz.wglj.suzhou.com.cn/scenic-spot-detail.aspx?id=58) / `visitsz.wglj.suzhou.com.cn` | 政府 |
| `candidate.2026-11-18.suzhou-jiangsu.tiger-hill-scenic-area-huqiu` | 苏州虎丘山风景名胜区：7:30开园，11-4月至17:30、5-10月至18:00，17:00停止售票 | 苏州（江苏） | 景点参观、行程规划 | [苏州市旅游咨询中心（苏州市文化广电和旅游局主管）景区介绍页《虎丘山风景名胜区》](https://visitsz.wglj.suzhou.com.cn/scenic-spot-detail.aspx?id=55) / `visitsz.wglj.suzhou.com.cn` | 政府 |
| `candidate.2026-11-18.shanghai.yu-garden-yuyuan` | 上海豫园（日间游览）：9:00-16:30开放、16:00停止入园 | 上海 | 景点参观、行程规划 | [上海市政府网站《31家景区（点）生日免票福利来了！》（来源：黄浦区人民政府）](https://www.shanghai.gov.cn/nw17239/20260519/b4cc7db33efe486b83f02e1b9dc4b712.html) / `www.shanghai.gov.cn` | 政府 |
| `candidate.2026-11-18.shanghai.yu-garden-night-tour-yu-xiang-shan-lin` | 上海豫园夜游《豫享山林》：按季节分时段开放，需按预约时段从南门入园 | 上海 | 景点参观、节假日与季节 | [上海市政府英文网站《Yuyuan Garden unveils new tour experience》](https://english.shanghai.gov.cn/en-UniqueExperience-travelinshanghai/20250729/25cfb8bce97d4e798f99ac62986255ff.html) / `english.shanghai.gov.cn` | 政府 |
| `candidate.2026-11-18.shanghai.zhujiajiao-ancient-town` | 上海朱家角古镇：景点联票含课植园等3处，景点每天8:30-17:00，需先到游客中心换纸质票 | 上海 | 景点参观、支付、亲子 | [朱家角古镇旅游区官网《门票预订》（上海朱家角古镇旅游发展有限公司）](https://zhujiajiao.com/cn/ticket/) / `zhujiajiao.com` | 场馆/景区官方 |
| `candidate.2026-11-18.shanghai.zhujiajiao-ancient-town-getting-there` | 上海朱家角交通：地铁17号线朱家角站换乘公交或步行进镇，另有沪朱高速快线 | 上海 | 城市与城际交通、抵达与住宿登记 | [朱家角古镇旅游区官网《交通指南》（上海朱家角古镇旅游发展有限公司）](https://zhujiajiao.com/cn/traffic/) / `zhujiajiao.com` | 场馆/景区官方 |
| `candidate.2026-11-18.shanghai.shanghai-science-and-technology-museum` | 上海科技馆：2026年2月17日起试开放，周二至周日9:00-17:00、周一闭馆，全员线上实名预约 | 上海 | 景点参观、护照预约与购票、亲子 | [上海市文化和旅游局网站《马年首展！上海科技馆大年初一试开放》（来源：乐游上海）](https://whlyj.sh.gov.cn/wbzx/20260211/96b8e43e2d7c478895adfd26fcc27fbc.html) / `whlyj.sh.gov.cn` | 政府 |

## 首次来华基础（支付、上网、抵达、铁路、住宿登记、退税、求助渠道）

文件：[2026-11-18-first-time-basics.json](2026-11-18-first-time-basics.json)，14 条。

| id | 标题 | 城市 | 主题 | 来源（名称 / 域名） | 来源类型 |
|---|---|---|---|---|---|
| `candidate.2026-11-18.nationwide.rail-12306-ticketing` | 12306英文官网：境外旅客实名购票、可用证件与身份核验 | 全国 | 铁路/高铁、城市与城际交通 | [中国铁路12306英文版 常见问题（Ticketing）](https://www.12306.cn/en/faq.html) / `www.12306.cn` | 交通运营方 |
| `candidate.2026-11-18.nationwide.rail-12306-change-refund` | 12306英文官网：改签、退票与儿童票常见规则 | 全国 | 铁路/高铁、城市与城际交通、亲子 | [中国铁路12306英文版 常见问题（Endorsement and refund / Miscellaneous）](https://www.12306.cn/en/faq.html) / `www.12306.cn` | 交通运营方 |
| `candidate.2026-11-18.beijing.beijing-capital-international-airport-terminals-2-3` | 北京首都国际机场：机场巴士、出租车、网约车与市区接驳 | 北京 | 城市与城际交通、抵达与住宿登记 | [北京首都国际机场官网 交通信息-往来机场](https://www.bcia.com.cn/wljc.html) / `www.bcia.com.cn` | 交通运营方 |
| `candidate.2026-11-18.beijing.beijing-daxing-international-airport` | 北京大兴国际机场：地铁大兴机场线与城际铁路接驳市区 | 北京 | 城市与城际交通、抵达与住宿登记、铁路/高铁 | [首都之窗（北京市人民政府门户）交通一体化专题报道](https://www.beijing.gov.cn/ywdt/zwzt/jjjyth/jtxx/202501/t20250109_3984893.html) / `www.beijing.gov.cn` | 政府 |
| `candidate.2026-11-18.shanghai.shanghai-pudong-international-airport-shanghai-hongqiao-international-airport` | 上海浦东、虹桥机场：轨道交通与机场巴士接驳 | 上海 | 城市与城际交通、抵达与住宿登记、铁路/高铁 | [上海机场（集团）有限公司官网 机场交通-轨道交通](https://www.shanghaiairport.com/gdjt/index.html) / `www.shanghaiairport.com` | 交通运营方 |
| `candidate.2026-11-18.guangzhou.guangzhou-baiyun-international-airport-terminal-3` | 广州白云机场T3航站楼：城际、地铁与接驳公交进城方式 | 广州 | 城市与城际交通、抵达与住宿登记、铁路/高铁 | [广东省人民政府门户网站 便民提示](https://www.gd.gov.cn/zwfw/bmts/content/mpost_4893706.html) / `www.gd.gov.cn` | 政府 |
| `candidate.2026-11-18.chengdu.chengdu-tianfu-international-airport` | 成都天府国际机场：地铁18/19号线、机场专线与其他接驳 | 成都 | 城市与城际交通、抵达与住宿登记、铁路/高铁 | [成都天府国际机场官网 交通-综合交通](https://www.sctfia.com/traffic/tramode/metro/metro.html?id=608) / `www.sctfia.com` | 交通运营方 |
| `candidate.2026-11-18.nationwide.payment-guide` | 外国人在华移动支付与银行卡：政府指引要点 | 全国 | 支付 | [中国政府网英文版 Guide to Working and Living in China（2025年版，商务部供稿）](https://english.www.gov.cn/2025special/bizexpatsinchina2025) / `english.www.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.wechat-pay-foreign-card` | 微信支付：境外银行卡绑定与使用说明（官方帮助中心） | 全国 | 支付 | [WeChat 帮助中心《微信支付外卡绑定和使用指南》](https://cs.help.wechat.com/hc/zh-cn/articles/11975770896271-%E5%BE%AE%E4%BF%A1%E6%94%AF%E4%BB%98%E5%A4%96%E5%8D%A1%E7%BB%91%E5%AE%9A%E5%92%8C%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97) / `cs.help.wechat.com` | 商业平台 |
| `candidate.2026-11-18.nationwide.sim-card-guide` | 境外手机号与在华SIM卡：政府指引中的办理方式 | 全国 | 上网/手机卡 | [中国政府网英文版 Guide to Working and Living in China（2025年版，商务部供稿）](https://english.www.gov.cn/2025special/bizexpatsinchina2025) / `english.www.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.accommodation-registration` | 入境后住宿登记：酒店代办与24小时内派出所登记 | 全国 | 抵达与住宿登记 | [中国政府网英文版 Guide to Working and Living in China（2025年版，商务部供稿）](https://english.www.gov.cn/2025special/bizexpatsinchina2025) / `english.www.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.departure-tax-refund` | 离境退税：税务总局2026年优化服务通知要点 | 全国 | 支付 | [中国政府网 国务院部门文件《国家税务总局关于优化离境退税服务推动政策规范落实的通知》](https://www.gov.cn/zhengce/zhengceku/202607/content_7075798.htm) / `www.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.12367-hotline` | 国家移民管理机构12367服务平台：多语种出入境咨询渠道 | 全国 | 签证入境官方渠道 | [中国政府网《国家移民管理机构12367服务平台和英文版门户网站答问解读》](https://www.gov.cn/xinwen/2021-04/08/content_5598376.htm) / `www.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.mfa-global-consular-protection-and-service-emergency-hotline-12308` | 12308领事保护热线的适用边界（候选，需判断是否适用于外国游客） | 全国 | 紧急求助 | [中国领事服务网 12308领保热线](https://cs.mfa.gov.cn/zggmcgx/lsbhyxz/12308lbrx/202607/t20260713_11981004.html) / `cs.mfa.gov.cn` | 政府 |

## 北方及其他热门城市景点（北京、青岛、哈尔滨、昆明、张家界、洛阳）

文件：[2026-11-18-north-other-cities.json](2026-11-18-north-other-cities.json)，12 条。

| id | 标题 | 城市 | 主题 | 来源（名称 / 域名） | 来源类型 |
|---|---|---|---|---|---|
| `candidate.2026-11-18.beijing.temple-of-heaven` | 天坛公园开放时间、古建闭馆日与外语导览服务（官网） | 北京 | 景点参观、行程规划 | [天坛公园官网（北京市天坛公园管理处）](https://tiantanpark.cn/guide_service.html) / `tiantanpark.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.beijing.summer-palace` | 颐和园开放时间、园中园周一闭园与游船季节性运营（官网导览页） | 北京 | 景点参观、城市与城际交通、行程规划、节假日与季节 | [颐和园官网（导览页）](https://www.summerpalace.net.cn/visit.html) / `www.summerpalace.net.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.beijing.national-museum-of-china` | 中国国家博物馆参观预约制度与开放时间（官网预约须知） | 北京 | 景点参观、行程规划、护照预约与购票 | [中国国家博物馆官网（参观预约）](https://www.chnmuseum.cn/cg/cgyy/202511/t20251109_277547.shtml) / `www.chnmuseum.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.beijing.mutianyu-great-wall` | 慕田峪长城开放时间、实名预约与限购规则（景区官网） | 北京 | 景点参观、行程规划、节假日与季节 | [慕田峪长城旅游网（北京市慕田峪长城旅游服务有限公司）](https://www.mutianyugreatwall.com/) / `www.mutianyugreatwall.com` | 场馆/景区官方 |
| `candidate.2026-11-18.luoyang.longmen-grottoes` | 龙门石窟门票与开放时间（英文官网购票页） | 洛阳 | 景点参观、行程规划、节假日与季节 | [龙门石窟官方网站（英文站）](https://en.lmsk.cn/Pwxx_id_2.html) / `en.lmsk.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.luoyang.longmen-grottoes-2` | 龙门石窟到达方式与景区内交通（英文官网交通页） | 洛阳 | 城市与城际交通、景点参观、行程规划 | [龙门石窟官方网站（英文站·交通页）](https://en.lmsk.cn/Pwxx_id_3.html) / `en.lmsk.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.qingdao.tsingtao-beer-museum` | 青岛啤酒博物馆分季开放时间与入馆核验规则（官网参观须知） | 青岛 | 景点参观、亲子、节假日与季节 | [青岛啤酒博物馆官网（参观须知）](https://www.tsingtaomuseum.com/articleTitleCus/1790371205849559041?viewName=newCanguanDetail) / `www.tsingtaomuseum.com` | 场馆/景区官方 |
| `candidate.2026-11-18.qingdao.zhanqiao-pier-huilan-pavilion` | 青岛栈桥与回澜阁当前开放状态（修缮期间，2026年10月公告） | 青岛 | 景点参观、行程规划 | [观海新闻（青岛日报社）转引青岛海滨景区管理服务中心公告](https://www.guanhai.com.cn/p/478661.html) / `www.guanhai.com.cn` | 官方媒体/政府新闻 |
| `candidate.2026-11-18.harbin.harbin-ice-and-snow-world` | 哈尔滨冰雪大世界季节性运营、票务政策与交通指引（运营方官网） | 哈尔滨 | 景点参观、城市与城际交通、节假日与季节、行程规划、亲子 | [哈尔滨冰雪大世界官网（哈尔滨冰雪大世界股份有限公司）](https://ice.hrbicesnow.com/) / `ice.hrbicesnow.com` | 场馆/景区官方 |
| `candidate.2026-11-18.kunming.stone-forest-shilin` | 昆明石林风景区实名制票务与入园方式（昆明市政府门户转载报道） | 昆明 | 景点参观、行程规划 | [昆明市人民政府门户网站（转载昆明日报）](https://www.km.gov.cn/c/2025-02-12/4943494.shtml) / `www.km.gov.cn` | 政府 |
| `candidate.2026-11-18.zhangjiajie.zhangjiajie-national-forest-park-wulingyuan` | 张家界武陵源（国家森林公园）分时预约、门票有效期与南门交通（商业票务平台） | 张家界 | 景点参观、城市与城际交通、行程规划 | [张家界国家森林公园门票预约预订系统（第三方票务平台）](https://www.zhangjiajieforestpark.com/ticket/forest-gate-copy-copy?lang=zh-CN) / `www.zhangjiajieforestpark.com` | 商业平台 |
| `candidate.2026-11-18.kunming.dianchi-lake-greenway` | 滇池绿道观光车、接驳车、租赁车与观鸥季交通攻略（度假区管委会） | 昆明 | 城市与城际交通、景点参观、节假日与季节、行程规划 | [昆明滇池国家旅游度假区管委会（政务要闻）](https://dianchi.km.gov.cn/c/2026-11-13/7198124.shtml) / `dianchi.km.gov.cn` | 政府 |

## 行程规划与官方渠道（节假日、无障碍、亲子、季节、签证入境渠道）

文件：[2026-11-18-planning-and-channels.json](2026-11-18-planning-and-channels.json)，12 条。

| id | 标题 | 城市 | 主题 | 来源（名称 / 域名） | 来源类型 |
|---|---|---|---|---|---|
| `candidate.2026-11-18.nationwide.holiday-2026` | 国务院办公厅关于2026年部分节假日安排的通知（中国政府网发布页） | 全国 | 行程规划、节假日与季节 | [中国政府网（国务院办公厅）](https://www.gov.cn/zhengce/content/202511/content_7047090.htm) / `www.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.holiday-2027` | 国务院办公厅关于2027年部分节假日安排的通知（中国政府网发布页） | 全国 | 行程规划、节假日与季节 | [中国政府网（国务院办公厅）](https://www.gov.cn/zhengce/content/202611/content_7085101.htm) / `www.gov.cn` | 政府 |
| `candidate.2026-11-18.beijing.beijing-subway-network` | 北京地铁全路网无障碍出行服务与预约方式（首都之窗转载北京日报报道） | 北京 | 无障碍、城市与城际交通 | [北京市人民政府门户网站（首都之窗）](https://www.beijing.gov.cn/fuwu/bmfw/sy/jrts/202605/t20260518_4654955.html) / `www.beijing.gov.cn` | 政府 |
| `candidate.2026-11-18.guangzhou.guangzhou-metro-network` | 广州地铁无障碍设施与“爱心直通车”预约（广州市政府门户转载广州日报报道） | 广州 | 无障碍、城市与城际交通 | [广州市人民政府门户网站](https://www.gz.gov.cn/zwfw/zxfw/jtfw/content/post_10566207.html) / `www.gz.gov.cn` | 政府 |
| `candidate.2026-11-18.shenzhen.shenzhen-metro` | 深圳地铁无障碍设施介绍（官网“无障碍乘车指南”栏目） | 深圳 | 无障碍、城市与城际交通 | [深圳地铁（深圳市地铁集团有限公司）](https://www.szmc.net/shentieyunying/yunyingzixun/wuzhangaichengchezhinan/wuzhangaisheshi/) / `www.szmc.net` | 交通运营方 |
| `candidate.2026-11-18.shanghai.shanghai-museum` | 上海博物馆无障碍与婴儿车、轮椅服务（官网英文服务页） | 上海 | 无障碍、亲子 | [上海博物馆](https://www.shanghaimuseum.net/mu/frontend/pg/en/service/) / `www.shanghaimuseum.net` | 场馆/景区官方 |
| `candidate.2026-11-18.beijing.national-museum-of-china-2` | 中国国家博物馆无障碍电梯与暑期服务升级（官网“国博要闻”） | 北京 | 无障碍、节假日与季节 | [中国国家博物馆](https://www.chnmuseum.cn/zx/gbxw/202608/t20260813_281865.shtml) / `www.chnmuseum.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.nationwide.rail-12306-child-tickets` | 中国铁路12306儿童购票常见问题（官网“出行指南”） | 全国 | 亲子、铁路/高铁 | [中国铁路12306（中国国家铁路集团有限公司）](https://kyfw.12306.cn/otn/gonggao/children.html) / `kyfw.12306.cn` | 交通运营方 |
| `candidate.2026-11-18.nationwide.nia-foreigners-guide-en` | 国家移民管理局英文官网“外国人指南”栏目（官方出入境查询渠道） | 全国 | 签证入境官方渠道 | [国家移民管理局（National Immigration Administration）](https://en.nia.gov.cn/n147423/n147478/index.html) / `en.nia.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.mfa-visiting-china` | 中国领事服务网“外国公民来华”官方信息入口（外交部） | 全国 | 签证入境官方渠道 | [中国领事服务网（中华人民共和国外交部）](https://cs.mfa.gov.cn/) / `cs.mfa.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.visaforchina-entry` | 中国签证申请服务中心（CVASC）官网入口 | 全国 | 签证入境官方渠道 | [中国签证申请服务中心（CVASC）](https://www.visaforchina.cn/) / `www.visaforchina.cn` | 其他公开来源 |
| `candidate.2026-11-18.nationwide.mct-seasonal-safety-tip` | 文化和旅游部：端午节假期和汛期、暑期出游提示（2026-06-05） | 全国 | 节假日与季节、行程规划 | [中华人民共和国文化和旅游部](https://www.mct.gov.cn/whzx/whyw/202606/t20260605_966153.htm) / `www.mct.gov.cn` | 政府 |

## 华南与东南城市景点（广州、深圳、桂林、厦门）

文件：[2026-11-18-south-cities.json](2026-11-18-south-cities.json)，12 条。

| id | 标题 | 城市 | 主题 | 来源（名称 / 域名） | 来源类型 |
|---|---|---|---|---|---|
| `candidate.2026-11-18.guangzhou.canton-tower` | 广州塔：营业时间与到达方式（海珠区政府门户网站） | 广州 | 景点参观、城市与城际交通 | [广州市海珠区人民政府门户网站](https://www.haizhu.gov.cn/hzdt/ztlm/tzhz/rjhj/lyjd/csmp/content/post_9190964.html) / `www.haizhu.gov.cn` | 政府 |
| `candidate.2026-11-18.guangzhou.baiyun-mountain-scenic-area` | 白云山风景名胜区：购票优惠、门岗到达与园内交通 | 广州 | 景点参观、城市与城际交通、亲子 | [白云山风景区门户网站（广州市白云山风景名胜区管理局）](https://www.baiyunshan.com.cn/bys/jqzn/jqzn.shtml) / `www.baiyunshan.com.cn` | 场馆/景区官方 |
| `candidate.2026-11-18.guangzhou.chen-clan-ancestral-hall-guangdong-folk-art-museum` | 陈家祠（广东民间工艺博物馆）：开放时间与预约渠道 | 广州 | 景点参观 | [广州市人民政府门户网站（广州市文化广电旅游局信息）](https://www.gz.gov.cn/zwgk/zdly/shgysyjs/ggwhty/ggwh/content/post_9864493.html) / `www.gz.gov.cn` | 政府 |
| `candidate.2026-11-18.guangzhou.guangdong-museum` | 广东省博物馆：开放时间、实名预约与入馆核验 | 广州 | 景点参观 | [广州市人民政府门户网站（广州市文化广电旅游局信息）](https://www.gz.gov.cn/zwgk/zdly/shgysyjs/ggwhty/ggwh/content/post_9864493.html) / `www.gz.gov.cn` | 政府 |
| `candidate.2026-11-18.shenzhen.shenzhen-museum` | 深圳博物馆：免预约入馆与场馆开放时间 | 深圳 | 景点参观、亲子、无障碍 | [深圳市文化广电旅游体育局网站](https://wtl.sz.gov.cn/xxgk/qt/gzdt/content/post_12102133.html) / `wtl.sz.gov.cn` | 政府 |
| `candidate.2026-11-18.shenzhen.dapeng-fortress-dapeng-ancient-city` | 大鹏所城：政府答复中的开放时间与联系方式 | 深圳 | 景点参观 | [深圳市大鹏新区政府在线](https://www.dpxq.gov.cn/hdjlpt/detail?pid=2759505) / `www.dpxq.gov.cn` | 政府 |
| `candidate.2026-11-18.guilin.elephant-trunk-hill-xiangshan-scenic-area` | 象鼻山（象山景区）：开放时间、游客中心与公共交通到达 | 桂林 | 景点参观、城市与城际交通 | [桂林两江四湖·象山景区官方网站](https://www.glljsh.com/) / `www.glljsh.com` | 场馆/景区官方 |
| `candidate.2026-11-18.guilin.li-river-cruise-li-river-scenic-area` | 漓江游船：实名线上预约与售票渠道 | 桂林 | 景点参观、护照预约与购票 | [桂林漓江景区旅游官网（桂林漓江风景名胜区市场拓展处）](https://www.liriver.com.cn/page/article/zxlj.tzgg/269) / `www.liriver.com.cn` | 政府 |
| `candidate.2026-11-18.xiamen.xiamen-ferry-xiamen-gulangyu-routes` | 厦门轮渡（厦鼓航线）：游客乘船、证件与返程规则 | 厦门 | 城市与城际交通、护照预约与购票、抵达与住宿登记 | [厦门轮渡有限公司官网](https://m.xmferry.com/xwdt/wshlk/xchgpp/) / `m.xmferry.com` | 交通运营方 |
| `candidate.2026-11-18.guilin.two-rivers-and-four-lakes` | 两江四湖：游览区构成与游船售票时段 | 桂林 | 景点参观 | [桂林两江四湖·象山景区官方网站](https://www.glljsh.com/scenic/ljsh.html) / `www.glljsh.com` | 场馆/景区官方 |
| `candidate.2026-11-18.xiamen.gulangyu-island` | 鼓浪屿：官方小程序、讲解服务与码头便民设施 | 厦门 | 景点参观、行程规划、亲子 | [厦门市人民政府门户网站](https://www.xm.gov.cn/jdhy/rdhy/202407/t20240722_2879674.htm) / `www.xm.gov.cn` | 政府 |
| `candidate.2026-11-18.xiamen.sunlight-rock-riguangyan-gulangyu` | 日光岩（鼓浪屿）：分季开放时间、地址与讲解场次 | 厦门 | 景点参观 | [厦门市鼓浪屿文化旅游发展中心官网](https://www.glyylq.cn/article.php?id=158) / `www.glyylq.cn` | 场馆/景区官方 |

## 人工补充的官方渠道与住宿登记（国家移民管理局）

文件：[2026-11-18-visa-entry-channels.json](2026-11-18-visa-entry-channels.json)，2 条。

| id | 标题 | 城市 | 主题 | 来源（名称 / 域名） | 来源类型 |
|---|---|---|---|---|---|
| `candidate.2026-11-18.nationwide.nia-online-accommodation-registration` | 国家移民管理局：外国人非酒店住宿登记自2026-09-21起可全国线上办理（候选） | 全国 | 抵达与住宿登记 | [国家移民管理局公告（2026年第7号，英文版）](https://en.nia.gov.cn/n147418/n147468/c237295/content.html) / `en.nia.gov.cn` | 政府 |
| `candidate.2026-11-18.nationwide.nia-english-policy-interpretation` | 国家移民管理局英文站：入境与免签政策官方解读栏目（查询渠道） | 全国 | 签证入境官方渠道 | [国家移民管理局英文门户 Policy Interpretation](https://en.nia.gov.cn/n147418/n147463/index.html) / `en.nia.gov.cn` | 政府 |

## 后续处理

1. 查重：重点核对上方“共用同一来源 URL”的条目，以及同城同景点的多个条目（如豫园日游/夜游、龙门石窟门票/交通）。
2. 复核：先处理有 `conflicts` 的条目与本批缺口最大的一手来源（机场、博物馆官网反爬导致的政府门户转述）。
3. 来源批准：按 `../SOURCES.md` 与 #702 流程登记来源范围后，才可写入正式 `entries-v3/`。
4. 未核实的未知字段保留在 `missing`，不因晋级而删除。
