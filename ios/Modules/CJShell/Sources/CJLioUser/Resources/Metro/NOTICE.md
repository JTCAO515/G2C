# 地铁图数据来源清单（#1450）

每座城市一份随包文件 `LioMetroMap.<城市>.v1.json`，文件内 `source` 与 `cityInfo` 是唯一事实来源；本表由文件生成。

- 运营方数据：北京、上海、广州、深圳、西安的线路、站序、换乘与中文站名取自运营方官网（见各行链接）。
- 高德参考：其余城市按 JT 2026-11-25 决定，以高德地图地铁线网图的布局与站点为参考，转成我们自己的随包地图；页面来源行写「线路与站点：参考高德地图地铁线网图，核对于某日」。未使用高德 Web 服务 key，原始响应不入仓库。
- 英文站名（JT 2026-11-25「先找英文、再用拼音」）：运营方英文 > 高德英文 > 维基百科车站列表（与高德拼音交叉核对，疑似错行改用拼音）> 站名拼音。

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
| 长春（changchun） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/changchun-2201） | 站名拼音 | 2026-11-25 |
| 常州（changzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/changzhou-3204） | 站名拼音 | 2026-11-25 |
| 大连（dalian） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/dalian-2102） | 维基百科大连地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 福州（fuzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/fuzhou-3501） | 站名拼音 | 2026-11-25 |
| 哈尔滨（haerbin） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/haerbin-2301） | 站名拼音 | 2026-11-25 |
| 合肥（hefei） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/hefei-3401） | 站名拼音 | 2026-11-25 |
| 呼和浩特（huhehaote） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/huhehaote-1501） | 站名拼音 | 2026-11-25 |
| 济南（jinan） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/jinan-3701） | 站名拼音 | 2026-11-25 |
| 兰州（lanzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/lanzhou-6201） | 站名拼音 | 2026-11-25 |
| 洛阳（luoyang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/luoyang-4103） | 站名拼音 | 2026-11-25 |
| 南昌（nanchang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/nanchang-3601） | 站名拼音 | 2026-11-25 |
| 南京（nanjing） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/nanjing-3201） | 维基百科南京地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 南通（nantong） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/nantong-3206） | 站名拼音 | 2026-11-25 |
| 宁波（ningbo） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/ningbo-3302） | 高德地图英文站名；未提供的用拼音 | 2026-11-25 |
| 青岛（qingdao） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/qingdao-3702） | 站名拼音 | 2026-11-25 |
| 绍兴（shaoxing） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/shaoxing-3306） | 高德地图英文站名；未提供的用拼音 | 2026-11-25 |
| 沈阳（shenyang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/shenyang-2101） | 站名拼音 | 2026-11-25 |
| 石家庄（shijiazhuang） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/shijiazhuang-1301） | 维基百科石家庄地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 苏州（suzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/suzhou-3205） | 站名拼音 | 2026-11-25 |
| 太原（taiyuan） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/taiyuan-1401） | 站名拼音 | 2026-11-25 |
| 天津（tianjin） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/tianjin-1200） | 维基百科天津地铁车站列表；未收录的站用拼音 | 2026-11-25 |
| 乌鲁木齐（wulumuqi） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/wulumuqi-6501） | 站名拼音 | 2026-11-25 |
| 无锡（wuxi） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/wuxi-3202） | 站名拼音 | 2026-11-25 |
| 厦门（xiamen） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/xiamen-3502） | 站名拼音 | 2026-11-25 |
| 徐州（xuzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/xuzhou-3203） | 站名拼音 | 2026-11-25 |
| 郑州（zhengzhou） | 参考高德地图地铁线网图（https://www.amap.com/ssr/subway/zhengzhou-4101） | 维基百科郑州地铁车站列表；未收录的站用拼音 | 2026-11-25 |
