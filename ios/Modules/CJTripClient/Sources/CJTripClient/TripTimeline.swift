import Foundation

public enum TripTimelineSpan: Sendable, Equatable {
    case sameLocalDay
    case continuesTo(String)
    case differentZones
    case reversedLocalDates
    case undetermined
}
public struct TripTimelineEntry: Identifiable, Sendable {
    public let item: StructuredTripItem
    public let span: TripTimelineSpan
    public var id: String { item.id }
}
public struct TripTimelineGroup: Identifiable, Sendable {
    public let date: String?
    public let timezone: String?
    public let entries: [TripTimelineEntry]
    public var id: String {
        if let date,let timezone { return date+"|"+timezone }
        return "undetermined"
    }
}

/// Read-only projection of the accepted content. Each global item ID appears
/// exactly once at its explicitly declared start day/zone. Group and item order
/// retain first appearance in the accepted plan, not inferred device instants.
public struct TripTimeline: Sendable {
    public let contentSHA256: String
    public let groups: [TripTimelineGroup]
    public init(document: StructuredTripDocument) {
        contentSHA256=document.contentSHA256
        var keys: [String]=[],dates: [String:(String?,String?)]=[:],entries: [String:[TripTimelineEntry]]=[:]
        for item in document.items {
            let date: String?,zone: String?
            if case .known(let day)=item.start.date,case .known(let name)=item.start.timezone { date=day;zone=name }
            else { date=nil;zone=nil }
            let key: String
            if let date,let zone { key=date+"|"+zone } else { key="undetermined" }
            if entries[key]==nil { keys.append(key);dates[key]=(date,zone);entries[key]=[] }
            entries[key]!.append(.init(item:item,span:Self.span(item)))
        }
        groups=keys.map { key in .init(date:dates[key]!.0,timezone:dates[key]!.1,entries:entries[key]!) }
    }
    private static func span(_ item: StructuredTripItem) -> TripTimelineSpan {
        guard case .known(let start)=item.start.date,case .known(let end)=item.end.date,
              case .known(let fromZone)=item.start.timezone,case .known(let toZone)=item.end.timezone else { return .undetermined }
        guard same(fromZone,toZone) else { return .differentZones }
        if end<start { return .reversedLocalDates }
        return end==start ? .sameLocalDay : .continuesTo(end)
    }
}
