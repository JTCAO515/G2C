# Gaode profile source record

Checked 2026-10-22 (Asia/Shanghai) using official read-only documentation, no
business request/key/account. Implementation pins v3, not the newer v5 shape.

| Official source | Applied facts |
|---|---|
| [POI search/detail](https://lbs.amap.com/api/webservice/guide/api-advanced/search) (page updated 2026-07-15) | `/v3/place/text`, `/v3/place/detail`; one keyword/one detail ID; citylimit, children, extensions, pagination, langCode; status 1 success, 0 failure; detail refers to search response format. POI ID, parent, name/address, location, entr_location, exit_location, navi_poiid. Missing values can be arrays; exit content is currently not provided. Detail and multilingual access may need advanced permission. |
| [Directions](https://lbs.amap.com/api/webservice/guide/api/direction) | v3 walking/driving endpoints; longitude first, at most six fractional digits; walking origin_id/destination_id versus driving originid/destinationid; driving strategy 10. Response route.origin/destination/paths; distance in meters, duration estimated seconds. These selected modes have no supported explicit departure parameter in this slice. |
| [Error codes](https://lbs.amap.com/api/webservice/guide/tools/info) (page updated 2022-10-12) | 10000 success. Rate codes 10003/10004/10010/10014/10015/10019/10020/10021/10029/10044/10045 explicitly quota/QPS. Other failures retain numeric code; 20801/20802 are provider errors, not successful empty results. No textual error matching or automatic retry. |
| [Coordinate basics](https://lbs.amap.com/api/javascript-api-v2/guide/abc/basetype) | Gaode uses GCJ-02; preserve it, do not claim WGS84 or implement conversion. |

The direction URL timed out through web open twice; its official indexed content
was read through site-restricted search, including walking/driving request and
response sections. The POI detail table was read in context: the following AOI
v5 section has different success semantics and is **not** used by this parser.

Adapter-specific conservative policy (not represented as provider guarantees):
UTF-8 input bytes, positive explicit limits, narrow string numeric/status profile,
32-level JSON nesting maximum, exact required structure/count checks, no redirect
support, per-page bound 25/page end 200, optional unsupported values retained as
invalid/null, explicit-time requests refused. Final outbound signed URL/streaming
limits and authenticated dispatch remain future host responsibilities.
