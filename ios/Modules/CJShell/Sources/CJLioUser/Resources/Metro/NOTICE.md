# 地铁图数据来源清单（#1450）

每座城市一份随包文件 `LioMetroMap.<城市>.v1.json`，文件内 `source` 与 `cityInfo` 是唯一事实来源；本表由文件生成。

- 运营方数据：北京、上海、广州、深圳、西安的线路、站序、换乘与中文站名取自运营方官网（见各行链接）。
- 高德参考：其余城市按 JT 2026-11-25 决定，以高德地图地铁线网图的布局与站点为参考，转成我们自己的随包地图；页面来源行写「线路与站点：参考高德地图地铁线网图，核对于某日」。未使用高德 Web 服务 key，原始响应不入仓库。
- 英文站名（JT 2026-11-25「先找英文、再用拼音」）：运营方英文 > 高德英文 > 维基百科车站列表（与高德拼音交叉核对，疑似错行改用拼音）> 站名拼音。
- 车站坐标（`geo`，GCJ-02）：取自同一份高德地铁线网数据中的车站点，只作站点周边查询的中心点（JT 2026-11-25 批准，授权条目 12⑤）；不随包存放任何周边地点数据。运营方城市里高德尚未收录的个别新站没有坐标，这些站不提供周边查询。
- 线路颜色（#2008，2026-11-27）：北京、上海、广州、深圳、重庆的线路色按运营方官网数字色值（北京、深圳取官网 SVG 线路描边，上海取官网线网图 SVG，广州取官方线路选择标签，重庆取官网行程规划线路标签）；成都运营方只以图片发布线路色，未能取得文字色值，仍用原有颜色。其余城市颜色沿用高德线网图。
- 重点站配图（#2008）：站点与收录库地点的对应写在 `LioMetroStationPlaces.v1.json`，图片由收录库提供，标注「示意图」。

## 整城移除

删除该城的 `LioMetroMap.<城市>.v1.json` 并重新生成本表即可：城市列表、地图与测试都按随包文件自动列出，无需改代码。

## 城市

| 城市 | 线路与站点 | 英文站名 | 核对日期 |
|---|---|---|---|
| 北京（beijing） | 北京地铁官网（https://map.bjsubway.com/、https://map_en.bjsubway.com/） | 运营方官网 | 2026-11-24 |
| 上海（shanghai） | 上海地铁官网（https://service.shmetro.com/czxx/index.htm、https://service.shmetro.com/en/czxx/index.htm） | 运营方官网 | 2026-11-24 |
| 广州（guangzhou） | 广州地铁官网（https://wx.gzmtr.com:50443/#/index?language=Cn、https://cs.gzmtr.com/ckfw/） | 运营方官网 | 2026-11-24 |
| 深圳（shenzhen） | 深圳地铁官网（https://www.szmc.net/map/） | 运营方官网 | 2026-11-25 |
| 成都（chengdu） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/chengdu-5101） | 维基百科成都地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 杭州（hangzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/hangzhou-3301） | 高德地图英文站名；未提供的用维基百科车站列表或拼音 | 2026-11-25 |
| 西安（xian） | 西安地铁官网（https://m.xianrail.com/metroRoute） | 维基百科西安地铁车站列表（站名标识拼音） | 2026-11-25 |
| 重庆（chongqing） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/chongqing-5000） | 维基百科重庆地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 长春（changchun） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/changchun-2201） | 站名拼音 | 2026-11-25 |
| 长沙（changsha） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/changsha-4301） | 站名拼音 | 2026-11-25 |
| 常州（changzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/changzhou-3204） | 站名拼音 | 2026-11-25 |
| 大连（dalian） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/dalian-2102） | 维基百科大连地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 东莞（dongguan） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/dongguan-4419） | 站名拼音 | 2026-11-25 |
| 佛山（foshan） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/foshan-4406） | 与广州共用的站用广州地铁官网英文；其余用站名拼音 | 2026-11-25 |
| 福州（fuzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/fuzhou-3501） | 站名拼音 | 2026-11-25 |
| 贵阳（guiyang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/guiyang-5201） | 站名拼音 | 2026-11-25 |
| 哈尔滨（haerbin） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/haerbin-2301） | 站名拼音 | 2026-11-25 |
| 合肥（hefei） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/hefei-3401） | 站名拼音 | 2026-11-25 |
| 呼和浩特（huhehaote） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/huhehaote-1501） | 站名拼音 | 2026-11-25 |
| 济南（jinan） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/jinan-3701） | 站名拼音 | 2026-11-25 |
| 昆明（kunming） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/kunming-5301） | 站名拼音 | 2026-11-25 |
| 兰州（lanzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/lanzhou-6201） | 站名拼音 | 2026-11-25 |
| 洛阳（luoyang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/luoyang-4103） | 站名拼音 | 2026-11-25 |
| 南昌（nanchang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/nanchang-3601） | 站名拼音 | 2026-11-25 |
| 南京（nanjing） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/nanjing-3201） | 维基百科南京地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 南宁（nanning） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/nanning-4501） | 站名拼音 | 2026-11-25 |
| 南通（nantong） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/nantong-3206） | 站名拼音 | 2026-11-25 |
| 宁波（ningbo） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/ningbo-3302） | 高德地图英文站名；未提供的用拼音 | 2026-11-25 |
| 青岛（qingdao） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/qingdao-3702） | 站名拼音 | 2026-11-25 |
| 绍兴（shaoxing） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/shaoxing-3306） | 高德地图英文站名；未提供的用拼音 | 2026-11-25 |
| 沈阳（shenyang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/shenyang-2101） | 站名拼音 | 2026-11-25 |
| 石家庄（shijiazhuang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/shijiazhuang-1301） | 维基百科石家庄地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 苏州（suzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/suzhou-3205） | 站名拼音 | 2026-11-25 |
| 太原（taiyuan） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/taiyuan-1401） | 站名拼音 | 2026-11-25 |
| 天津（tianjin） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/tianjin-1200） | 维基百科天津地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 武汉（wuhan） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/wuhan-4201） | 维基百科武汉地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 乌鲁木齐（wulumuqi） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/wulumuqi-6501） | 站名拼音 | 2026-11-25 |
| 无锡（wuxi） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/wuxi-3202） | 站名拼音 | 2026-11-25 |
| 厦门（xiamen） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/xiamen-3502） | 站名拼音 | 2026-11-25 |
| 徐州（xuzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/xuzhou-3203） | 站名拼音 | 2026-11-25 |
| 郑州（zhengzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/zhengzhou-4101） | 维基百科郑州地铁车站列表；未收录的站用拼音 | 2026-11-25 |
