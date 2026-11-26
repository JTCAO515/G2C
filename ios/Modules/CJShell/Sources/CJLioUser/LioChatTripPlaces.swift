import CJMessageHTTP
import CJTripClient
import Foundation

/// #1723 PR-2: `G2CChatTripPlacesEnabled` in the build's Info.plist; off unless it says YES. Off, saving a chat
/// plan is exactly the summary save it always was and nothing is read from the network.
enum LioChatTripPlacesFeature {
    static let infoKey = "G2CChatTripPlacesEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    static var enabledInBuild: Bool { enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) }
}

/// The server trip a chat card (LIO-trip-card.3) names: its id, version and content hash. A card.2 has no
/// structured.4 places to read, so it has no reference.
struct LioChatTripReference: Equatable, Sendable {
    let tripID: String
    let tripVersion: Int64
    let contentSHA256: String

    init(tripID: String, tripVersion: Int64, contentSHA256: String) {
        self.tripID = tripID; self.tripVersion = tripVersion; self.contentSHA256 = contentSHA256
    }

    init?(_ trip: LioExplorationWire.Trip) {
        guard case .rich(let card) = trip else { return nil }
        self.init(tripID: card.id, tripVersion: card.tripVersion, contentSHA256: card.contentSHA256)
    }
}

/// #1723 PR-2: before a chat plan is saved, reads the account's current copy of that trip
/// (`GET /v7/trip-structured?trip_id=`, TRIP-structured-read.3) for its places' addresses and GCJ-02 points.
///
/// The server does not compare versions; this does. Same version and content hash as the card: the read's
/// places are used. A higher version: the trip changed since the card, so the whole record is replaced by the
/// new version. A lower version, the same version with another hash, `trip: null`, any failure, or no answer
/// within `timeout`: the card's summary is saved as before (every place unconfirmed). Saving never fails here.
/// Only the trip id is sent; no coordinate or address is logged.
@MainActor public struct LioChatTripPlaces: Sendable {
    public typealias Read = @MainActor @Sendable (String) async throws -> LioTimelineHTTP.TripStructuredResponse

    enum Failure: Error, Equatable, Sendable {
        /// 503 TRIP_UNAVAILABLE after the last retry.
        case unavailable
        /// Any other status (401, 400, an unexpected 503, ...): not retried.
        case status(Int)
        /// No response (offline, transport error, no credential).
        case network
        /// Nothing usable before the deadline.
        case timeout
        /// A body that is too large, not strict read.3 / structured.4, or names another trip.
        case invalid
    }
    enum Outcome: Equatable, Sendable {
        /// The flag is off or the plan is not this card's: nothing was read.
        case notRead
        case confirmed
        case replaced
        /// A lower version, or the same version with a different hash.
        case conflicting
        /// `trip: null` (absent, another account's, or an old format).
        case missing
        case failed(Failure)
    }

    static let maximumBytes = LioTimelineHTTP.tripStructuredMaximumBytes

    let enabled: Bool
    let maximumRetries: Int
    let timeout: Duration
    private let read: Read
    private let pause: @Sendable (Duration) async throws -> Void

    /// The signed reader; on only when the build turns `G2CChatTripPlacesEnabled` on.
    public static func signed(_ client: LioTimelineHTTP) -> Self {
        Self(enabled: LioChatTripPlacesFeature.enabledInBuild, read: { try await client.readTripStructured(tripID: $0) })
    }

    init(enabled: Bool, read: @escaping Read, maximumRetries: Int = 2, timeout: Duration = .seconds(8),
         pause: @escaping @Sendable (Duration) async throws -> Void = { try await Task.sleep(for: $0) }) {
        self.enabled = enabled
        self.read = read
        self.maximumRetries = maximumRetries
        self.timeout = timeout
        self.pause = pause
    }

    /// The plan to save for this card, and how it was decided. Always returns a plan.
    func plan(for reference: LioChatTripReference, summary: LioPlanSummary) async -> (plan: LioPlanSummary, outcome: Outcome) {
        guard enabled, summary.source == .chat, summary.tripID == reference.tripID,
              summary.tripVersion == reference.tripVersion else { return (summary, .notRead) }
        let tripID = reference.tripID
        let fetched = await LioDeadline.run(timeout: timeout) { [self] in await fetch(tripID) }
        switch fetched {
        case nil: return (summary, .failed(.timeout))
        case .failure(let failure)?: return (summary, .failed(failure))
        case .success(let record)?: return Self.reconcile(reference, summary: summary, record: record)
        }
    }

    private func fetch(_ tripID: String) async -> Result<RichStructuredTripRecord?, Failure> {
        var retries = 0
        while true {
            let response: LioTimelineHTTP.TripStructuredResponse
            do {
                response = try await read(tripID)
            } catch {
                return .failure(Task.isCancelled ? .timeout : .network)
            }
            if Task.isCancelled { return .failure(.timeout) }
            switch response.status {
            case 200:
                guard response.bytes.count <= Self.maximumBytes, let trace = response.requestID else { return .failure(.invalid) }
                let record: RichStructuredTripRecord?
                do {
                    record = try RichStructuredTripReadV3.detail(response.bytes, requestID: trace)
                } catch {
                    return .failure(.invalid)
                }
                if let record, record.tripID != tripID { return .failure(.invalid) }
                return .success(record)
            case 503 where Self.retrySafeRead(response.bytes):
                guard retries < maximumRetries else { return .failure(.unavailable) }
                do {
                    try await pause(Self.backoff(retries))
                } catch {
                    return .failure(.timeout)
                }
                if Task.isCancelled { return .failure(.timeout) }
                retries += 1
            default:
                return .failure(.status(response.status))
            }
        }
    }

    /// 0.5 s, then 1 s: two retries fit well inside the 8 s deadline.
    static func backoff(_ retry: Int) -> Duration { .milliseconds(500 << min(retry, 4)) }

    /// Only the route's own 503 TRIP_UNAVAILABLE / retry_safe_read is retried; a proxy's 503 is not.
    static func retrySafeRead(_ bytes: Data) -> Bool {
        guard bytes.count <= 65_536,
              let root = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let error = root["error"] as? [String: Any] else { return false }
        return error["code"] as? String == "TRIP_UNAVAILABLE" && error["recovery"] as? String == "retry_safe_read"
    }

    /// The App's comparison of the read against the card (the server compares nothing).
    static func reconcile(_ reference: LioChatTripReference, summary: LioPlanSummary,
                          record: RichStructuredTripRecord?) -> (plan: LioPlanSummary, outcome: Outcome) {
        guard let record else { return (summary, .missing) }
        guard record.tripID == reference.tripID else { return (summary, .failed(.invalid)) }
        let version = Int64(record.version)
        if version > reference.tripVersion {
            // Changed since the card: the newer version replaces the whole record, not just its places.
            guard case .rich(let document) = record.content,
                  let replaced = try? LioPlanSummary(chatTripID: record.tripID, version: version, document: document) else {
                return (summary, .failed(.invalid))
            }
            return (replaced, .replaced)
        }
        guard version == reference.tripVersion, record.content.contentSHA256 == reference.contentSHA256 else {
            return (summary, .conflicting)
        }
        guard case .rich(let document) = record.content, let confirmed = try? summary.confirmingPlaces(document) else {
            return (summary, .failed(.invalid))
        }
        return (confirmed, .confirmed)
    }
}

/// Resolves with the work's value, or nil once `timeout` passes first (the work is then cancelled and its late
/// value ignored). A transport that ignores cancellation cannot hold the caller past the deadline.
@MainActor private final class LioDeadline<Value: Sendable> {
    private var continuation: CheckedContinuation<Value?, Never>?
    private var worker: Task<Void, Never>?
    private var timer: Task<Void, Never>?

    static func run(timeout: Duration, _ work: @escaping @MainActor @Sendable () async -> Value) async -> Value? {
        let deadline = LioDeadline<Value>()
        return await withCheckedContinuation { continuation in
            Task { @MainActor in deadline.start(continuation, timeout: timeout, work) }
        }
    }

    private func start(_ continuation: CheckedContinuation<Value?, Never>, timeout: Duration,
                       _ work: @escaping @MainActor @Sendable () async -> Value) {
        self.continuation = continuation
        worker = Task { @MainActor in
            let value = await work()
            self.resolve(value, timedOut: false)
        }
        timer = Task { @MainActor in
            try? await Task.sleep(for: timeout)
            guard !Task.isCancelled else { return }
            self.resolve(nil, timedOut: true)
        }
    }

    private func resolve(_ value: Value?, timedOut: Bool) {
        guard let continuation else { return }
        self.continuation = nil
        if timedOut { worker?.cancel() } else { timer?.cancel() }
        continuation.resume(returning: value)
    }
}

// MARK: - Mapping the read into the saved trip

enum LioChatTripMappingFailure: Error { case invalid }

extension LioRichItinerary.Kind {
    init(chatKind kind: RichStructuredTripDocument.Kind) {
        switch kind {
        case .sight: self = .sight
        case .meal: self = .meal
        case .hotel: self = .hotel
        case .transport: self = .transport
        case .freeTime: self = .freeTime
        }
    }
}

extension LioRichItinerary.Place {
    /// Only a matched place keeps its address and its original GCJ-02 point (no conversion); an unconfirmed one
    /// keeps its Chinese and English names, unconfirmed, without an address or point.
    init(chatPlace source: RichStructuredTripDocument.Place) throws {
        guard LioPublicDisplay.permitsText(source.nameZH), LioPublicDisplay.permitsText(source.nameEN) else {
            throw LioChatTripMappingFailure.invalid
        }
        guard source.matched else {
            self.init(nameZH: source.nameZH, nameEN: source.nameEN, address: nil, matched: false, point: nil)
            return
        }
        guard let coordinate = source.coordinate, source.address.map(LioPublicDisplay.permitsText) ?? true else {
            throw LioChatTripMappingFailure.invalid
        }
        let latitude = NSDecimalNumber(decimal: coordinate.latitude.value).doubleValue
        let longitude = NSDecimalNumber(decimal: coordinate.longitude.value).doubleValue
        guard latitude.isFinite, longitude.isFinite, (-90...90).contains(latitude), (-180...180).contains(longitude) else {
            throw LioChatTripMappingFailure.invalid
        }
        self.init(nameZH: source.nameZH, nameEN: source.nameEN, address: source.address, matched: true,
                  point: LioItinerary.Point(latitude: latitude, longitude: longitude))
    }
}

extension LioPlanSummary {
    /// The same trip, version and content as the card: its stops take the read's kinds and places. Times, days and
    /// everything else stay as the card gave them.
    func confirmingPlaces(_ document: RichStructuredTripDocument) throws -> LioPlanSummary {
        var items: [String: RichStructuredTripDocument.Item] = [:]
        for item in document.items {
            guard items.updateValue(item, forKey: item.calendarItem.value.id) == nil else { throw LioChatTripMappingFailure.invalid }
        }
        let stops = itinerary.days.flatMap(\.stops)
        guard stops.count == items.count, Set(stops.map(\.id)) == Set(items.keys) else { throw LioChatTripMappingFailure.invalid }
        let days = try itinerary.days.map { day in
            LioRichItinerary.Day(number: day.number, date: day.date, theme: day.theme, area: day.area, stops: try day.stops.map { stop in
                guard let item = items[stop.id], item.calendarItem.startDayIndex == day.number else {
                    throw LioChatTripMappingFailure.invalid
                }
                return LioRichItinerary.Stop(id: stop.id, kind: .init(chatKind: item.kind), text: stop.text, time: stop.time,
                                             place: try .init(chatPlace: item.place), note: stop.note, tip: stop.tip, fixed: stop.fixed)
            }, legs: day.legs)
        }
        return LioPlanSummary(tripID: tripID, tripVersion: tripVersion, source: source, startDate: startDate,
                              itinerary: LioRichItinerary(title: itinerary.title, undated: itinerary.undated, days: days,
                                                          lodgingArea: itinerary.lodgingArea, hotels: itinerary.hotels))
    }

    /// A newer version of a chat trip than its card: the whole trip from that version's content (start times, as a
    /// card gives them; kinds, places, notes, tips, legs and lodging from the content).
    init(chatTripID: String, version: Int64, document: RichStructuredTripDocument) throws {
        var visible = [document.title, document.lodging.area]
        for day in document.days { visible += [day.theme, day.area] }
        for item in document.items { visible += [item.calendarItem.value.text, item.note, item.tip?.text].compactMap { $0 } }
        visible += document.lodging.recommendations.compactMap(\.note)
        guard visible.allSatisfy(LioPublicDisplay.permitsText) else { throw LioChatTripMappingFailure.invalid }

        func leg(_ source: RichStructuredTripDocument.Leg) throws -> LioRichItinerary.Leg {
            guard let value = source.estimate else { return .init(fromID: source.fromItemID, toID: source.toItemID, estimate: nil) }
            guard let seconds = Double(value.duration.token), seconds.isFinite, seconds >= 0,
                  let metres = Double(value.distance.token), metres.isFinite, metres >= 0 else {
                throw LioChatTripMappingFailure.invalid
            }
            let mode: LioRichItinerary.Leg.Mode
            switch value.mode { case .walking: mode = .walking; case .transit: mode = .transit; case .taxi: mode = .taxi }
            return .init(fromID: source.fromItemID, toID: source.toItemID, estimate: .init(mode: mode, seconds: seconds, metres: metres))
        }
        let days = try document.days.map { day in
            try LioRichItinerary.Day(number: day.index, date: day.date, theme: day.theme, area: day.area,
                stops: document.items.filter { $0.calendarItem.startDayIndex == day.index }.map { item in
                    let value = item.calendarItem.value
                    return LioRichItinerary.Stop(id: value.id, kind: .init(chatKind: item.kind), text: value.text,
                                                 time: value.start.time.lioValue, place: try .init(chatPlace: item.place),
                                                 note: item.note, tip: item.tip?.text, fixed: value.fixed.lioValue)
                },
                legs: document.legs.filter { $0.dayIndex == day.index }.map(leg))
        }
        let hotels = try document.lodging.recommendations.enumerated().map { index, hotel in
            LioRichItinerary.Hotel(id: "lodging.\(index)", place: try .init(chatPlace: hotel.place), note: hotel.note)
        }
        let start: String?
        switch document.calendar { case .dated(let date): start = date; case .undated: start = nil }
        self.init(tripID: chatTripID, tripVersion: version, source: .chat, startDate: start,
                  itinerary: LioRichItinerary(title: document.title, undated: start == nil, days: days,
                                              lodgingArea: document.lodging.area, hotels: hotels))
    }
}
