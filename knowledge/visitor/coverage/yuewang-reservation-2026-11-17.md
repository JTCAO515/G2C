# 岳王庙整体普通预约补证

关联#1058；2026-11-17实际核读。只将既有整体岳王庙条目的reservation_required从null补为true；普通周闭[]/假日例外false、原subject、QID=null、未知提前天数及语义、checked11-17/expires11-23均保持。新增0、修改1，不将内部岳飞纪念馆记录改成整个岳庙。

来源范围及核读记录为[#702/6949762163](https://github.com/JTCAO515/G2C/issues/702#issuecomment-6949762163)。[去哪儿精确主记录](https://sight.qunar.com/833)明确浙江杭州北山路80号，并介绍忠烈祠和岳飞父子墓园。入园信息下的门票预订信息单列费用、预约及公众号；其中明确要求提前预约，没有具体SKU、供应商套餐、某日库存或某类人群限定。本条据这一平台普通入园陈述记录true，不从可预订或商品下单截止倒推全馆制度。

平台无资料独立更新时间，页脚品牌/ICP备案只是自报，不冒园方确认或外部资质核验；未具名公众号、护照线上字段、拼接电话、优惠资格和西湖一日游评论均不采用。未核最少提前天数或窗口，不把需要提前预约说成必须提前一天；也不拿2023仅至3月底的免费期预约说明冒当前确认。普通星期规则继续单独由既有整体门户报道支持，临时安排及当日可入另核，平台说明不覆盖所有内部设施。

独立R源预核PASS仅说明这一一般入园字段的对象和语义足够，不是最终head APPROVE。本批与草堂/三园、大雁塔/莲花山一并在PR1140交付，精确head独立R、全部CI成功、锁head合并及向L通知仍待，不提前计交付或关票。只加本精确URL的杭州场馆许可及正反例，其他目录、旧格式、FACT wire和原负例不改。未访问订票/登录/地图/接口/跨host资质，无新Wiki、坐标、凭据、费用或原件日志入库。11-22 18:00北京前实际复核仍UNRUN，失效日不顺延。

## #1058 十一目标的本批候选核对

下表是原十一目标，上海博物馆两院区分列条件但仍计一个目标；内设岳飞纪念馆不替代整体岳庙，也不额外计目标。各记录的原来源、核对/失效日和中英限制照各自文件保留，未重新核读的既有记录不机械改日期。下表为合并前候选，不能据本表提前关闭票或宣称现场通过。

| 目标 / subject | 预约 | 普通周闭 |
|---|---|---|
| 豫园 / shanghai.yu-garden | false | 周一，法定假日例外 |
| 上博 / shanghai.museum-peoples-square、shanghai.museum-east | 人民广场true、东馆false | 人民广场周一、东馆周二，法定假日例外 |
| 外滩公共空间 / shanghai.the-bund | false | [] |
| 岳王庙整体 / hangzhou.yuewang-temple | true | [] |
| 西溪普通园区 / hangzhou.xixi-national-wetland-park | false | [] |
| 西湖公共湖岸 / hangzhou.west-lake | false | [] |
| 三峡博物馆 / chongqing.three-gorges-museum | false | 周一，法定假日例外 |
| 重庆动物园 / chongqing.zoo | false | [] |
| 深博历史民俗馆 / shenzhen.museum-history-folk | false | 周一，法定假日例外 |
| 莲花山普通游园 / shenzhen.lianhua-hill-park | false | [] |
| 世界之窗 / shenzhen.window-of-the-world | false | [] |

本组提前天数及语义均仍null，不由预约true/false推最少提前要求；[]项的假日周闭例外为false，不保证没有天气、活动或局部临时调整。记录见[沪深渝](../entries-v3/venues-shanghai-shenzhen.json)、[杭州](../entries-v3/venues-hangzhou.json)、[岳庙整体](../entries-v3/hangzhou-yuewang-temple.json)及[莲花山](../entries-v3/parks-shenzhen.json)。原23目标中仍未核的核心预约为草堂、府城墙和宿州三角洲公园，#1057/#1059继续开放；内设场馆的未知亦不外推补齐。
