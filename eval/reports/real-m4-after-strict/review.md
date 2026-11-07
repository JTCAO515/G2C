# JT 独立事实/语义审阅包

候选 `c9adb9a15b6ec366201ad4d89d821ae010292b48`，阶段 `hk-strict-10000-smoke-001`。只含本轮冒烟；正式66仍UNRUN。人工已审0；完整回答只证明通路，事实/语言/严重错误仍UNKNOWN。JT逐条填事实是否支持、表达是否清楚、错误严重程度和依据；不需要配置服务或提供密钥。

## place-route / zh — PASS

问题：合成旅行冒烟：先用place_search查询北京故宫、景山公园各1个地点，city北京/page1/page_size1。仅复制实际结果的POI ID、原始GCJ-02坐标和点角色，用place_route查询两点walking路线。根据实际来源说明查询时估计及未知项，不创建或保存行程。

RUN：71c8adba-97cb-4bf4-b205-4b3d83cc893e

回答：
来源：https://restapi.amap.com/v3/place/text
来源：https://restapi.amap.com/v3/place/text
来源：https://restapi.amap.com/v3/direction/walking
合成冒烟测试已完成（未创建或保存行程），结果来自实际高德查询。

地点：
- 故宫博物院：provider_id B000A8UIN8；GCJ-02 poi_center 坐标 116.397029,39.917839；地址“景山前街4号”；typecode 110201|140100；入口/出口坐标缺失。
- 景山公园：provider_id B000A7I1OL；GCJ-02 poi_center 坐标 116.396551,39.925875；地址“景山西街44号”；typecode 110101；入口/出口坐标缺失。

步行路线（两点均使用 poi_center）：距离 1,445 米，用时 1,156 秒（约 19 分 16 秒）。这是查询时估计（time_semantics=provider_estimate_at_query_time），出发时间为 null，future_guaranteed=false；具体未来出发条件下的路线不保证。

来源：place_search 分别查询“故宫”“景山公园”（高德 v3 place/text，接收时间 2026-11-07T02:49:14Z、02:49:16Z），随后 place_route 查询步行路线（高德 v3 direction/walking，接收时间 2026-11-07T02:49:20Z）。未知项：基于入口/出口的步行距离与时间、门址细节、开放时间、门票、实时人流及未来路线准确性。

来源：

```json
{
  "tool": "place",
  "name": "place_search",
  "actual_result": {
    "outcome": "ok",
    "places": [
      {
        "address_zh": {
          "state": "present",
          "value": "景山前街4号"
        },
        "coordinate": {
          "state": "present",
          "value": {
            "crs": "GCJ-02",
            "latitude": "39.917839",
            "longitude": "116.397029",
            "raw": "116.397029,39.917839"
          }
        },
        "entrance_coordinate": {
          "state": "missing",
          "value": null
        },
        "exit_coordinate": {
          "state": "missing",
          "value": null
        },
        "name_zh": "故宫博物院",
        "navigation_id": {
          "state": "missing",
          "value": null
        },
        "official_address_en": {
          "state": "unknown",
          "value": null
        },
        "official_name_en": {
          "state": "unknown",
          "value": null
        },
        "parent_id": {
          "state": "empty_array",
          "value": null
        },
        "provider": "gaode",
        "provider_id": "B000A8UIN8",
        "typecode": {
          "state": "present",
          "value": "110201|140100"
        }
      }
    ],
    "provider_code": "10000",
    "provider_count": 100,
    "query": {
      "city": "北京",
      "keyword": "故宫",
      "kind": "Search",
      "page": 1,
      "page_size": 1
    },
    "reason": "page_results",
    "routes": [],
    "source": {
      "adapter_profile": "CJ-PLACE-GAODE@0.1.0-rc.1",
      "api_version": "v3",
      "binding_digest": "c9ffb89d05807abca24ef8c65764d2cb37a66ec7801ed417b466c7849ffc5382",
      "endpoint": "https://restapi.amap.com/v3/place/text",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T02:49:14.029567+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T02:49:14.150014+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-0e88bd1e77dabf51fa87d8721e6f035c72b92192b925651a41bb6e11abf8cc31"
    },
    "version": "PLACE-result.1"
  }
}
```

```json
{
  "tool": "place",
  "name": "place_search",
  "actual_result": {
    "outcome": "ok",
    "places": [
      {
        "address_zh": {
          "state": "present",
          "value": "景山西街44号"
        },
        "coordinate": {
          "state": "present",
          "value": {
            "crs": "GCJ-02",
            "latitude": "39.925875",
            "longitude": "116.396551",
            "raw": "116.396551,39.925875"
          }
        },
        "entrance_coordinate": {
          "state": "missing",
          "value": null
        },
        "exit_coordinate": {
          "state": "missing",
          "value": null
        },
        "name_zh": "景山公园",
        "navigation_id": {
          "state": "missing",
          "value": null
        },
        "official_address_en": {
          "state": "unknown",
          "value": null
        },
        "official_name_en": {
          "state": "unknown",
          "value": null
        },
        "parent_id": {
          "state": "empty_array",
          "value": null
        },
        "provider": "gaode",
        "provider_id": "B000A7I1OL",
        "typecode": {
          "state": "present",
          "value": "110101"
        }
      }
    ],
    "provider_code": "10000",
    "provider_count": 96,
    "query": {
      "city": "北京",
      "keyword": "景山公园",
      "kind": "Search",
      "page": 1,
      "page_size": 1
    },
    "reason": "page_results",
    "routes": [],
    "source": {
      "adapter_profile": "CJ-PLACE-GAODE@0.1.0-rc.1",
      "api_version": "v3",
      "binding_digest": "8545db33341a1d77e0137e80fa8724e1490f62f7f4c856db39a5aa745401a641",
      "endpoint": "https://restapi.amap.com/v3/place/text",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T02:49:16.474055+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T02:49:16.575765+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-39fbaa8b2840a471cde4039f3cd93018970e57f4c02b372409ac29ad3cbcfec7"
    },
    "version": "PLACE-result.1"
  }
}
```

```json
{
  "tool": "place",
  "name": "place_route",
  "actual_result": {
    "outcome": "ok",
    "places": [],
    "provider_code": "10000",
    "provider_count": 1,
    "query": {
      "departure": {
        "at": null,
        "condition": "at_query_time"
      },
      "destination": {
        "coordinate": {
          "crs": "GCJ-02",
          "latitude": "39.925875",
          "longitude": "116.396551",
          "raw": "116.396551,39.925875"
        },
        "coordinate_role": "poi_center",
        "provider_id": "B000A7I1OL"
      },
      "kind": "RouteQuery",
      "mode": "walking",
      "origin": {
        "coordinate": {
          "crs": "GCJ-02",
          "latitude": "39.917839",
          "longitude": "116.397029",
          "raw": "116.397029,39.917839"
        },
        "coordinate_role": "poi_center",
        "provider_id": "B000A8UIN8"
      }
    },
    "reason": "route_estimates",
    "routes": [
      {
        "distance": {
          "state": "present",
          "value": {
            "raw": "1445",
            "unit": "m",
            "value": "1445"
          }
        },
        "duration": {
          "state": "present",
          "value": {
            "raw": "1156",
            "unit": "s",
            "value": "1156"
          }
        },
        "future_guaranteed": false,
        "query": {
          "departure": {
            "at": null,
            "condition": "at_query_time"
          },
          "destination": {
            "coordinate": {
              "crs": "GCJ-02",
              "latitude": "39.925875",
              "longitude": "116.396551",
              "raw": "116.396551,39.925875"
            },
            "coordinate_role": "poi_center",
            "provider_id": "B000A7I1OL"
          },
          "kind": "RouteQuery",
          "mode": "walking",
          "origin": {
            "coordinate": {
              "crs": "GCJ-02",
              "latitude": "39.917839",
              "longitude": "116.397029",
              "raw": "116.397029,39.917839"
            },
            "coordinate_role": "poi_center",
            "provider_id": "B000A8UIN8"
          }
        },
        "time_semantics": "provider_estimate_at_query_time"
      }
    ],
    "source": {
      "adapter_profile": "CJ-PLACE-GAODE@0.1.0-rc.1",
      "api_version": "v3",
      "binding_digest": "a1426c28c16ad6e4677d622f04ebea0ec83a1bf4e075487a8d3efa87f71bbf8d",
      "endpoint": "https://restapi.amap.com/v3/direction/walking",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T02:49:20.749005+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T02:49:20.793774+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-4c891d9c21c702532eeaef2893c2287ba2ce78914b7d57f40e07cb462705a626"
    },
    "version": "PLACE-result.1"
  }
}
```

疑点/待审：Please compare answer with these original result excerpts: POI identity, GCJ-02 point roles, 1445m/1156s, query-time caveat and stated unknowns; decide correctness, clarity and severity independently. No automatic serious-error zero certification.

事实/语言：UNKNOWN；严重错误：UNKNOWN；审阅人/日期/依据：待JT填。

## place-route / en — FAIL

问题：Synthetic travel smoke: use place_search for Forbidden City and Jingshan Park, Beijing, each page1/page_size1. Copy actual POI IDs, raw GCJ-02 coordinates and point roles into place_route for walking between them. Report query-time estimates, sources and unknowns; no trip write.

RUN：33fe95cc-7bb0-4d3c-bd72-30af70516bb3

回答：
（空正文；原 RUN UNKNOWN）

来源：
UNKNOWN / UNRUN：未产生实际来源回执。

疑点/待审：No answer or source produced: first native model envelope was rejected. Fact/semantic review cannot certify an empty answer; protocol failure is separately recorded.

事实/语言：UNKNOWN；严重错误：UNKNOWN；审阅人/日期/依据：待JT填。

## weather / zh — UNRUN

问题：合成天气冒烟：调用weather查询北京2026-11-08，start_date/end_date均为该日期，Asia/Shanghai。按返回来源、报告时点和未知项回答，不重复相同查询，不保存行程。

RUN：UNRUN

回答：
（未执行）

来源：
UNKNOWN / UNRUN：未产生实际来源回执。

疑点/待审：Not executed after stop; no answer or source evidence and no semantic verdict.

事实/语言：UNRUN；严重错误：UNRUN；审阅人/日期/依据：待JT填。

## weather / en — UNRUN

问题：Synthetic weather smoke: call weather for Beijing with start_date/end_date 2026-11-08, Asia/Shanghai. Answer using actual report time, source and unknowns; do not repeat the same query or write a trip.

RUN：UNRUN

回答：
（未执行）

来源：
UNKNOWN / UNRUN：未产生实际来源回执。

疑点/待审：Not executed after stop; no answer or source evidence and no semantic verdict.

事实/语言：UNRUN；严重错误：UNRUN；审阅人/日期/依据：待JT填。

## fact / zh — UNRUN

问题：合成事实冒烟：调用fact，start_date/end_date为2026-11-07。只根据官方国家移民管理局页面的实际摘录说明来源；旅客资格与日期适用性保持UNKNOWN。不编造、订票或保存行程。

RUN：UNRUN

回答：
（未执行）

来源：
UNKNOWN / UNRUN：未产生实际来源回执。

疑点/待审：Not executed after stop; no answer or source evidence and no semantic verdict.

事实/语言：UNRUN；严重错误：UNRUN；审阅人/日期/依据：待JT填。

## fact / en — UNRUN

问题：Synthetic fact smoke: call fact with start_date/end_date 2026-11-07. Answer only from actual official NIA page excerpts and cite source; traveler eligibility/date applicability stay UNKNOWN. No invented execution, booking or trip write.

RUN：UNRUN

回答：
（未执行）

来源：
UNKNOWN / UNRUN：未产生实际来源回执。

疑点/待审：Not executed after stop; no answer or source evidence and no semantic verdict.

事实/语言：UNRUN；严重错误：UNRUN；审阅人/日期/依据：待JT填。
