import Foundation
import CryptoKit
import Testing
@testable import CJTripClient

private func goldenPlaces() throws -> [[String: Any]] {
    let url = try #require(Bundle.module.url(forResource: "PLACE-V1", withExtension: "json", subdirectory: "Fixtures"))
    let bytes = try Data(contentsOf: url)
    #expect(SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() == "bc41082fe58d0ca7e6655dade3396e04fb61f10164fc897325d70615f39ebd53")
    let object = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
    #expect(object["data_origin"] as? String == "synthetic")
    return try #require(object["positive"] as? [[String: Any]])
}
private func placeBytes(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]) }
private func changedPlace(_ body: [String: Any], _ edit: (inout [String: Any]) -> Void) -> [String: Any] {
    var body=body, places=body["places"] as! [[String: Any]]; edit(&places[0]); body["places"]=places; return body
}

@Suite struct PlaceV1Tests {
    @Test func allSixFrozenGoldenResultsAndUnknownsArePreserved() throws {
        let golden = try goldenPlaces()
        #expect(golden.count == 6)
        let results = try golden.map { try PlaceResultV1.decode(placeBytes($0)) }
        #expect(results.map(\.outcome) == [.ok,.ok,.bindingMismatch,.noResults,.rateLimited,.unavailable])
        #expect(results[0].places.map(\.providerID) == ["SYNTH_EAST","SYNTH_WEST"])
        #expect(results[0].places[0].nameZH == results[0].places[1].nameZH)
        #expect(results[0].places[1].addressZH.state == .emptyArray)
        #expect(results[0].places[1].addressZH.value == nil)
        #expect(results[0].places.allSatisfy { $0.officialNameEN.state == .unknown && $0.officialNameEN.value == nil })
        #expect(results[0].source?.evidenceKind == "synthetic")
        #expect(results[0].source?.providerUpdatedAt == nil)
        #expect(results[5].source == nil)
        #expect(PlaceResultV1.contractVersion == "PLACE@1.0")
        #expect(PlaceResultV1.wireVersion == "PLACE-result.1")
    }
    @Test func decimalLexemesRolesAndZeroAreNotConvertedOrSubstituted() throws {
        var value=try goldenPlaces()[0]
        value=changedPlace(value) { place in
            place["coordinate"]=["state":"present","value":["raw":"-000.000000000000,0.000000000001","longitude":"-0.000000000000","latitude":"0.000000000001","crs":"GCJ-02"]]
        }
        let bytes=try placeBytes(value), result=try PlaceResultV1.decode(bytes), place=result.places[0]
        #expect(result.originalUTF8 == bytes)
        #expect(place.coordinate.value?.longitude.text == "-0.000000000000")
        #expect(place.coordinate.value?.latitude.text == "0.000000000001")
        #expect(place.coordinate.value?.latitude.value == Decimal(string:"0.000000000001"))
        #expect(place.coordinate(for: .entrance).value?.raw == "116.1001,39.1001")
        #expect(place.coordinate(for: .exit).state == .missing)
        #expect(place.coordinate(for: .exit).value == nil)
    }
    @Test func originalRouteEndpointsQuantitiesAndTimeSemanticsRemainBound() throws {
        let result=try PlaceResultV1.decode(placeBytes(goldenPlaces()[1]))
        guard case .route(let a,let b,let mode,let departure)=result.query else { Issue.record("route missing"); return }
        #expect(a.role == .entrance && b.role == .poiCenter && mode == "walking" && departure == .atQueryTime)
        #expect(result.routes[0].query == result.query)
        #expect(result.routes[0].distance.value?.amount.text == "100")
        #expect(result.routes[0].duration.value?.amount.text == "90")
        #expect(result.routes[0].distance.value?.unit == "m")
        #expect(!result.routes[0].futureGuaranteed)
    }
    @Test(arguments: ["missing","empty_array","empty_string","null","invalid","unknown"])
    func observationStatesStayDistinctAndNeverFillAnAddress(_ state: String) throws {
        let value=changedPlace(try goldenPlaces()[0]) { $0["address_zh"]=["state":state,"value":NSNull()] }
        let address=try PlaceResultV1.decode(placeBytes(value)).places[0].addressZH
        #expect(address.state.rawValue == state && address.value == nil)
    }
    @Test(arguments: Array(0..<31)) func actualDecoderRejectsFrozenNegativeSemantics(_ vector: Int) throws {
        var value=try goldenPlaces()[0]
        switch vector {
        case 0: value["accepted"]=true
        case 1: value["version"]="future"
        case 2: value["version"]="CJ-PLACE-TRIP-JSON@0.1.0-rc.1"
        case 3: value["provider_count"]=true
        case 4: value["provider_count"]=0
        case 5: var p=value["places"] as! [[String:Any]];p.append(p[0]);value["places"]=p
        case 6,7,8,9,10:
            value=changedPlace(value) { place in
                var observed=place["coordinate"] as! [String:Any], point=observed["value"] as! [String:Any]
                if vector==6 { point["longitude"]=116.1 }
                if vector==7 { point["longitude"]="116.2" }
                if vector==8 { point["crs"]="WGS84" }
                if vector==9 { point["raw"]="116.1,39.1\n";point["latitude"]="39.1\n" }
                if vector==10 { point["owner"]="forged" }
                observed["value"]=point;place["coordinate"]=observed
            }
        case 11: value=changedPlace(value) { $0["exit_coordinate"]=["state":"missing","value":["raw":"0,0","longitude":"0","latitude":"0","crs":"GCJ-02"]] }
        case 12...21:
            var source=value["source"] as! [String:Any]
            switch vector {
            case 12: source["endpoint"]="http://169.254.169.254/latest"
            case 13: source["max_age_seconds"]=999999
            case 14: source["evidence_kind"]="verified"
            case 15: source["evidence_kind"]="recorded_replay"
            case 16: source["query_started_at"]=["iso8601":"2026-10-22T12:00:00.000000","fold":0]
            case 17: source["received_at"]=["iso8601":"2026-10-22T12:00:01.000000+00:00","fold":true]
            case 18: source["received_at"]=["iso8601":"2026-10-22T11:59:59.000000+00:00","fold":0]
            case 19: source["received_at"]=["iso8601":"2026-02-30T12:00:01.000000+00:00","fold":0]
            case 20: source["provider_updated_at"]=["iso8601":"2026-10-22T12:00:01.000000+00:00","fold":0]
            default: source["recording_ref"]="not_a_recording"
            }
            value["source"]=source
        case 22: value["outcome"]="no_results"
        case 23: value["source"]=NSNull()
        case 24: value["places"]=[]
        case 25: value=changedPlace(value) { $0["provider_id"]="bad.id" }
        case 26: value=changedPlace(value) { $0["official_name_en"]=["state":"present","value":NSNull()] }
        case 27: value=changedPlace(value) { $0["address_zh"]=["state":"unknown","value":"filled default"] }
        case 28: var query=value["query"] as! [String:Any];query["page"]=true;value["query"]=query
        case 29: var query=value["query"] as! [String:Any];query["owner"]="forged";value["query"]=query
        default: value["reason"]="unsafe\n"
        }
        #expect(throws: TripFailure.invalidResponse) { try PlaceResultV1.decode(placeBytes(value)) }
    }
    @Test(arguments: ["2.0","2e0","true","-1","10000000000"])
    func countUsesOriginalJSONIntegerGrammar(_ token: String) throws {
        var value=try goldenPlaces()[0];value["provider_count"]=123456789
        let bytes=try placeBytes(value), text=String(decoding:bytes,as:UTF8.self).replacingOccurrences(of:"\"provider_count\":123456789",with:"\"provider_count\":"+token)
        #expect(throws: TripFailure.invalidResponse) { try PlaceResultV1.decode(Data(text.utf8)) }
    }
    @Test func duplicateKeysDepthBoundsAndMalformedJSONFailClosed() throws {
        let raw=try placeBytes(goldenPlaces()[0]),text=String(decoding:raw,as:UTF8.self)
        let duplicate=text.replacingOccurrences(of:"\"version\":",with:"\"version\":\"ignored\",\"version\":")
        for bytes in [Data(duplicate.utf8),Data((String(repeating:"[",count:1100)+"0"+String(repeating:"]",count:1100)).utf8),Data(repeating:32,count:1_048_577),Data("{\"version\":NaN}".utf8)] {
            #expect(throws: TripFailure.invalidResponse) { try PlaceResultV1.decode(bytes) }
        }
    }
    @Test func offsetFoldAndUnknownUpdatedTimeArePreservedWithoutDateInference() throws {
        var value=try goldenPlaces()[0],source=value["source"] as! [String:Any]
        source["query_started_at"]=["iso8601":"2026-10-22T20:00:00.000001+08:00","fold":1]
        source["received_at"]=["iso8601":"2026-10-22T12:00:00.000002+00:00","fold":0]
        value["source"]=source
        let result=try PlaceResultV1.decode(placeBytes(value))
        #expect(result.source?.started.fold == 1)
        #expect(result.source?.started.iso8601 == "2026-10-22T20:00:00.000001+08:00")
        #expect(result.source!.received.utcMicroseconds-result.source!.started.utcMicroseconds == 1)
        #expect(result.source?.providerUpdatedAt == nil)
    }
    @Test func routeCannotExchangeIDsRolesTimeOrInventFutureCertainty() throws {
        for vector in 0..<5 {
            var value=try goldenPlaces()[1],routes=value["routes"] as! [[String:Any]],route=routes[0]
            if vector==0 { route["future_guaranteed"]=true }
            if vector==1 { route["future_guaranteed"]=0 }
            if vector==2 { var q=route["query"] as! [String:Any],point=q["origin"] as! [String:Any];point["coordinate_role"]="poi_center";q["origin"]=point;route["query"]=q }
            if vector==3 { var observed=route["distance"] as! [String:Any],quantity=observed["value"] as! [String:Any];quantity["value"]=100;observed["value"]=quantity;route["distance"]=observed }
            if vector==4 {
                var q=value["query"] as! [String:Any];q["departure"]=["condition":"specified_time","at":["iso8601":"2027-01-01T00:00:00.000000+08:00","fold":0]];value["query"]=q;route["query"]=q
            }
            routes[0]=route;value["routes"]=routes
            #expect(throws: TripFailure.invalidResponse) { try PlaceResultV1.decode(placeBytes(value)) }
        }
    }
    @Test func unsupportedSpecifiedTimeRetainsExactConditionAndOriginalOffset() throws {
        var value=try goldenPlaces()[1], query=value["query"] as! [String:Any]
        query["departure"]=["condition":"specified_time","at":["iso8601":"2027-01-01T00:00:00.000000+08:00","fold":1]]
        value["query"]=query; value["routes"]=[]; value["outcome"]="unsupported"; value["reason"]="departure_not_supported"
        value["source"]=NSNull(); value["provider_count"]=NSNull(); value["provider_code"]=NSNull()
        let result=try PlaceResultV1.decode(placeBytes(value))
        guard case .route(_,_,_,.specifiedTime(let at))=result.query else { Issue.record("specified time defaulted away"); return }
        #expect(at.iso8601 == "2027-01-01T00:00:00.000000+08:00" && at.fold == 1)
        #expect(result.outcome == .unsupported && result.routes.isEmpty)
    }
    @Test func nestedUnknownFieldsAndRoutePrecisionAreNeverIgnored() throws {
        for vector in 0..<6 {
            var value=try goldenPlaces()[vector < 2 ? 0 : 1]
            if vector < 2 {
                value=changedPlace(value) { place in
                    if vector==0 { place["unknown"]=1 }
                    else { var o=place["address_zh"] as! [String:Any];o["fallback"]="invented";place["address_zh"]=o }
                }
            } else {
                var q=value["query"] as! [String:Any],routes=value["routes"] as! [[String:Any]],route=routes[0]
                if vector==2 { var dep=q["departure"] as! [String:Any];dep["default_time"]="now";q["departure"]=dep }
                if vector==3 { var point=q["origin"] as! [String:Any];point["coordinate_role"]="navigation";q["origin"]=point }
                if vector==4 {
                    var point=q["origin"] as! [String:Any]
                    point["coordinate"]=["raw":"116.1234567,39.1","longitude":"116.1234567","latitude":"39.1","crs":"GCJ-02"]
                    q["origin"]=point
                }
                if vector==5 { var qty=route["duration"] as! [String:Any];qty["extra"]=true;route["duration"]=qty }
                value["query"]=q;route["query"]=q;routes[0]=route;value["routes"]=routes
            }
            #expect(throws: TripFailure.invalidResponse) { try PlaceResultV1.decode(placeBytes(value)) }
        }
    }
    @Test func timeCanonicalityIncludesOffsetSecondsAndDoesNotInferFold() throws {
        var value=try goldenPlaces()[0],source=value["source"] as! [String:Any]
        source["query_started_at"]=["iso8601":"2026-10-22T12:00:30.000001+00:00:30.000001","fold":1]
        source["received_at"]=["iso8601":"2026-10-22T12:00:00.000001+00:00","fold":0]
        value["source"]=source
        let result=try PlaceResultV1.decode(placeBytes(value))
        #expect(result.source!.received.utcMicroseconds-result.source!.started.utcMicroseconds == 1)
        for time in ["2026-10-22T12:00:00.000000-00:00","2026-10-22T12:00:00.000000+00:00:00","2026-10-22T12:00:00.000000+00:00\n"] {
            source["query_started_at"]=["iso8601":time,"fold":0];value["source"]=source
            #expect(throws: TripFailure.invalidResponse) { try PlaceResultV1.decode(placeBytes(value)) }
        }
    }

}
