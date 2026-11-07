# JT 独立事实与语义审阅包

候选 `337e4d4e0147bc4197afa69781cac22908f152f1`，阶段 `hk-envelope-337-smoke-001`。正式 66 例 UNRUN，人工已审 0。请逐条记录来源是否支持、表述是否清楚、错误严重程度和依据。

## place-route / zh · PASS

合成旅行冒烟：先用place_search查询北京故宫、景山公园各1个地点，city北京/page1/page_size1。仅复制实际结果的POI ID、原始GCJ-02坐标和点角色，用place_route查询两点walking路线。根据实际来源说明查询时估计及未知项，不创建或保存行程。

RUN `aa4246f3-4497-4ce1-849d-fbb3cc1f509e`。人工判定 UNKNOWN。

### 原回答

来源：https://restapi.amap.com/v3/place/text
来源：https://restapi.amap.com/v3/place/text
来源：https://restapi.amap.com/v3/direction/walking
查询结果：

**故宫博物院**
- POI ID: B000A8UIN8（来源：高德/gaode）
- 坐标（GCJ-02）: 116.397029,39.917839（点角色：poi_center）
- 地址：景山前街4号
- 入口/出口坐标：缺失（missing）

**景山公园**
- POI ID: B000A7I1OL（来源：高德/gaode）
- 坐标（GCJ-02）: 116.396551,39.925875（点角色：poi_center）
- 地址：景山西街44号
- 入口/出口坐标：缺失（missing）

**步行路线估计（故宫 → 景山公园）**
- 距离：约 1445 米
- 时长：约 1156 秒（≈19 分钟）
- 时间语义：provider_estimate_at_query_time（仅为查询时刻的估计，不保证未来适用）

**未知项：**
- 两地的入口/出口精确坐标未提供，仅使用 poi_center。
- 出发时间未指定（departure.at = null），结果为查询时刻的静态估计。
- future_guaranteed = false，实际路况/路线可能变化。

本操作未创建或保存任何行程。

### 原工具结果 1 · place_search

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
      "binding_digest": "7f5c4939b238ed0f43dcda0e617f850bdb26d906d8d69906ab450fe5d11d6c80",
      "endpoint": "https://restapi.amap.com/v3/place/text",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:34.608723+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:34.729820+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-05068d9ebfea3be4de59f6d783a965a0bfc0707bbdcd2aedefe4ce2303ffd85f"
    },
    "version": "PLACE-result.1"
  }
}
```

### 原工具结果 2 · place_search

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
      "binding_digest": "43348cee808256cdf0d8a262108df6ee75c85744b2e94c540796940ba4ebb29a",
      "endpoint": "https://restapi.amap.com/v3/place/text",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:34.974064+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:35.068794+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-cf4ee64ca47ca78918648b28712e2139ba49aaddeac9e4627c9f633d86533d66"
    },
    "version": "PLACE-result.1"
  }
}
```

### 原工具结果 3 · place_route

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
      "binding_digest": "bd06837f739d690dcb0036301c4fb3854f99561ab4818c8d370e9a3737f3b55b",
      "endpoint": "https://restapi.amap.com/v3/direction/walking",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:37.404189+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:37.501146+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-139895fe14de2fb2619fd4ddcad3744c78e4c7437f2b93bf9c8a27e6f06a1b3e"
    },
    "version": "PLACE-result.1"
  }
}
```

## place-route / en · PASS

Synthetic travel smoke: use place_search for Forbidden City and Jingshan Park, Beijing, each page1/page_size1. Copy actual POI IDs, raw GCJ-02 coordinates and point roles into place_route for walking between them. Report query-time estimates, sources and unknowns; no trip write.

RUN `ffbb31e5-e998-4f60-b1f2-f4bf4be1d310`。人工判定 UNKNOWN。

### 原回答

Source: https://restapi.amap.com/v3/place/text
Source: https://restapi.amap.com/v3/place/text
Source: https://restapi.amap.com/v3/direction/walking
Query-time results (Gaode/Amap, GCJ-02):

- Forbidden City / 故宫博物院: provider_id B000A8UIN8; POI center 116.397029,39.917839; entrance/exit coordinates missing.
- Jingshan Park / 景山公园: provider_id B000A7I1OL; POI center 116.396551,39.925875; entrance/exit coordinates missing.

Walking route estimate using only POI centers:
- Distance: 1,445 m
- Duration: 1,156 s (~19 min 16 s)
- Semantics: provider_estimate_at_query_time; no future guarantee.

Unknowns: precise entrance/exit coordinates, navigation IDs, official English names/addresses, departure time (unspecified), live traffic and future route consistency. This is a query-time estimate only—not a trip write or confirmed booking.

### 原工具结果 1 · place_search

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
    "provider_count": 33,
    "query": {
      "city": "北京",
      "keyword": "Forbidden City",
      "kind": "Search",
      "page": 1,
      "page_size": 1
    },
    "reason": "page_results",
    "routes": [],
    "source": {
      "adapter_profile": "CJ-PLACE-GAODE@0.1.0-rc.1",
      "api_version": "v3",
      "binding_digest": "2504eac064f663f1e96f9169af508249c22e228efb2dbe684e38c72958943f23",
      "endpoint": "https://restapi.amap.com/v3/place/text",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:47.545332+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:47.729960+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-05071dfff66ff6f8d8debd42d929d1e817800d51f41fdf143a01e40172a916af"
    },
    "version": "PLACE-result.1"
  }
}
```

### 原工具结果 2 · place_search

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
    "provider_count": 72,
    "query": {
      "city": "北京",
      "keyword": "Jingshan Park",
      "kind": "Search",
      "page": 1,
      "page_size": 1
    },
    "reason": "page_results",
    "routes": [],
    "source": {
      "adapter_profile": "CJ-PLACE-GAODE@0.1.0-rc.1",
      "api_version": "v3",
      "binding_digest": "e8b7c0004668324e29351681ce5783714e3a3e61fbbc6cb0af5cae48126ce43f",
      "endpoint": "https://restapi.amap.com/v3/place/text",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:47.998652+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:48.163167+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-da9c397f5dda73fe603152ef509929910985301f3426a7d28f59bc1a7c89feaf"
    },
    "version": "PLACE-result.1"
  }
}
```

### 原工具结果 3 · place_route

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
      "binding_digest": "3912b127757fb15d16e1e020784a82caa10f033e99b3d53f2424f5e83e067e92",
      "endpoint": "https://restapi.amap.com/v3/direction/walking",
      "evidence_kind": "live_provider",
      "provider": "gaode",
      "provider_updated_at": null,
      "query_started_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:50.705452+00:00"
      },
      "received_at": {
        "fold": 0,
        "iso8601": "2026-11-07T03:48:50.807929+00:00"
      },
      "recording_ref": null,
      "request_ref": "op-784d23f7d87fd704337d88d723f5adc5d00285879a3b66a2f1b01629b1275d79"
    },
    "version": "PLACE-result.1"
  }
}
```

## weather / zh · PASS

合成天气冒烟：调用weather查询北京2026-11-08，start_date/end_date均为该日期，Asia/Shanghai。按返回来源、报告时点和未知项回答，不重复相同查询，不保存行程。

RUN `a78e8e62-503b-407f-bc8d-65e618ac656b`。人工判定 UNKNOWN。

### 原回答

来源：https://restapi.amap.com/v3/weather/weatherInfo
北京 2026-11-08（Asia/Shanghai）天气预报：白天雨夹雪，约 6°C，东北风 1-3 级；夜间多云，约 -4°C，东北风 1-3 级。

来源与观测情况：
- 返回来源：restapi.amap.com/v3/weather/weatherInfo（高德天气接口），地区 adcode 110000（北京）。
- 状态：status="observed"，但 reason="provider_forecast_not_future_guarantee" —— 这是提供方对该日历日期的预报数据，并非已发生的实况，也不构成对未来天气的保证。
- 提供方报告时点 provider_reporttime：2026-11-07 11:39:46；抓取时间 retrieved_at：2026-11-07T03:48:58Z（即北京时间 2026-11-07 11:48:58）。两者均在目标日期之前，说明该结果属于提前一天的预报。
- 原始数据校验：original_sha256=e471ef49…b41a12cf。

未知项（UNKNOWN）：
- actual_cost_cny：UNKNOWN（本查询不涉及费用，且提供方未返回该项）。
- 未提供降水概率、湿度、空气质量、体感温度等指标，均视为未知。
- week="7"、daypower/nightpower 等字段含义以提供方定义为准，未额外推断。

按要求仅执行了一次该日期的查询，未重复请求，也未保存任何行程或预订。

### 原工具结果 1 · weather

```json
{
  "tool": "weather",
  "name": "weather",
  "actual_result": {
    "actual_cost_cny": "UNKNOWN",
    "calendar_timezone": "Asia/Shanghai",
    "forecasts": [
      {
        "date": "2026-11-08",
        "daypower": "1-3",
        "daytemp": "6",
        "daytemp_float": "6.0",
        "dayweather": "雨夹雪",
        "daywind": "东北",
        "nightpower": "1-3",
        "nighttemp": "-4",
        "nighttemp_float": "-4.0",
        "nightweather": "多云",
        "nightwind": "东北",
        "week": "7"
      }
    ],
    "original_sha256": "e471ef495e4be1529e9a15fe35eab389f812dc5f03fac3e5ecf8f80bb41a12cf",
    "provider_reporttime": "2026-11-07 11:39:46",
    "reason": "provider_forecast_not_future_guarantee",
    "region_adcode": "110000",
    "retrieved_at": "2026-11-07T03:48:58.557679+00:00",
    "source_url": "https://restapi.amap.com/v3/weather/weatherInfo",
    "status": "observed"
  }
}
```

## weather / en · FAIL

Synthetic weather smoke: call weather for Beijing with start_date/end_date 2026-11-08, Asia/Shanghai. Answer using actual report time, source and unknowns; do not repeat the same query or write a trip.

RUN `74c45935-3c18-4ccb-999e-eacbf7f990e6`。人工判定 UNKNOWN。

### 原回答

Source: https://restapi.amap.com/v3/weather/weatherInfo


### 原工具结果 1 · weather

```json
{
  "tool": "weather",
  "name": "weather",
  "actual_result": {
    "actual_cost_cny": "UNKNOWN",
    "calendar_timezone": "Asia/Shanghai",
    "forecasts": [
      {
        "date": "2026-11-08",
        "daypower": "1-3",
        "daytemp": "6",
        "daytemp_float": "6.0",
        "dayweather": "雨夹雪",
        "daywind": "东北",
        "nightpower": "1-3",
        "nighttemp": "-4",
        "nighttemp_float": "-4.0",
        "nightweather": "多云",
        "nightwind": "东北",
        "week": "7"
      }
    ],
    "original_sha256": "e471ef495e4be1529e9a15fe35eab389f812dc5f03fac3e5ecf8f80bb41a12cf",
    "provider_reporttime": "2026-11-07 11:39:46",
    "reason": "provider_forecast_not_future_guarantee",
    "region_adcode": "110000",
    "retrieved_at": "2026-11-07T03:49:10.194230+00:00",
    "source_url": "https://restapi.amap.com/v3/weather/weatherInfo",
    "status": "observed"
  }
}
```

本格只有来源行，续接模型未交付有效正文。

## fact / zh · UNRUN

合成事实冒烟：调用fact，start_date/end_date为2026-11-07。只根据官方国家移民管理局页面的实际摘录说明来源；旅客资格与日期适用性保持UNKNOWN。不编造、订票或保存行程。

RUN `UNRUN`。人工判定 UNKNOWN。

## fact / en · UNRUN

Synthetic fact smoke: call fact with start_date/end_date 2026-11-07. Answer only from actual official NIA page excerpts and cite source; traveler eligibility/date applicability stay UNKNOWN. No invented execution, booking or trip write.

RUN `UNRUN`。人工判定 UNKNOWN。
