import Foundation
import Testing
@testable import CJTripClient

@Suite @MainActor struct TripTimelineTests {
    @Test func crossDayItemAppearsOnceAtItsDeclaredStartWithRawPrecision() throws {
        let f=try StructuredTripTests().fixture("minute"),doc=try StructuredTripDocument.decode(f.bytes),timeline=TripTimeline(document:doc)
        #expect(timeline.contentSHA256==f.sha256 && timeline.groups.count==1)
        #expect(timeline.groups[0].date=="2026-11-01" && timeline.groups[0].timezone=="Asia/Shanghai")
        #expect(timeline.groups[0].entries.map(\.id)==doc.items.map(\.id))
        #expect(timeline.groups[0].entries[0].span == .continuesTo("2026-11-02"))
        #expect(timeline.groups[0].entries[0].item.start.time == .known("23:00"))
        #expect(doc.originalUTF8==f.bytes)
    }
    @Test func unknownDateZoneAndProtectionNeverAcquireDeviceDefaults() throws {
        let f=try StructuredTripTests().fixture("unknown"),doc=try StructuredTripDocument.decode(f.bytes),timeline=TripTimeline(document:doc)
        #expect(timeline.groups.count==1 && timeline.groups[0].date==nil && timeline.groups[0].timezone==nil)
        #expect(timeline.groups[0].entries[0].span == .undetermined)
        #expect(timeline.groups[0].entries[0].item.start.date == .unknown)
        #expect(timeline.groups[0].entries[0].item.fixed == .unknown)
        #expect(doc.originalUTF8==f.bytes)
    }
    @Test func differentZonesDoNotInferACrossDayOrConvertTheRawDate() throws {
        let source=StructuredTripTests()
        let raw=try source.changedItem("explicit") { item in
            var schedule=item["schedule"] as! [String:Any],end=schedule["end"] as! [String:Any]
            end["timezone"]=["state":"known","value":"Europe/Paris"];schedule["end"]=end;item["schedule"]=schedule
        }
        let doc=try StructuredTripDocument.decode(raw),timeline=TripTimeline(document:doc)
        #expect(timeline.groups[0].entries[0].span == .differentZones)
        #expect(timeline.groups[0].date=="2026-11-01" && timeline.groups[0].timezone=="Asia/Shanghai")
        #expect(timeline.groups[0].entries[0].item.end.date == .known("2026-11-02"))
    }
    @Test func groupingRetainsAcceptedOrderAndAllGlobalIDsExactlyOnce() throws {
        let fixture=try StructuredTripTests().fixture("explicit")
        var value=try JSONSerialization.jsonObject(with:fixture.bytes) as! [String:Any]
        let first=(value["items"] as! [[String:Any]])[0];var second=first;second["id"]="second"
        var third=first;third["id"]="third"
        var schedule=third["schedule"] as! [String:Any],start=schedule["start"] as! [String:Any]
        start["date"]=["state":"unknown"];schedule["start"]=start;third["schedule"]=schedule
        value["items"]=[first,second,third]
        let bytes=try StructuredTripTests().canonical(value),doc=try StructuredTripDocument.decode(bytes),timeline=TripTimeline(document:doc)
        #expect(timeline.groups.count==2)
        let ids=timeline.groups.flatMap { $0.entries.map(\.id) }
        #expect(ids==doc.items.map(\.id) && Set(ids).count==3)
        #expect(timeline.groups.last?.date==nil)
    }
}
