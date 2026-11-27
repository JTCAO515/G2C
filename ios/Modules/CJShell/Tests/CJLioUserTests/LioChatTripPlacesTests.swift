import Foundation
import Testing
import CJMessageHTTP
import CJTripClient
@testable import CJLioUser

/// One-shot event a test waits on instead of the wall clock; firing first is remembered. A cancelled wait (the
/// test's time limit) stops waiting, so a regression fails the test rather than hanging it.
@MainActor private final class Signal {
    private var fired = false
    private var waiter: CheckedContinuation<Void, Never>?
    func fire() { fired = true; waiter?.resume(); waiter = nil }
    func wait() async {
        if fired { return }
        await withTaskCancellationHandler {
            await withCheckedContinuation { waiter = $0 }
        } onCancel: {
            Task { @MainActor in self.fire() }
        }
    }
}

/// A deadline the test completes by hand (`fire()`), standing in for `Task.sleep` so nothing here depends on how
/// fast the machine runs the rest of the suite. Cancelling the wait ends it, as cancelling a sleep does.
@MainActor private final class ManualDeadline {
    private(set) var requested: [Duration] = []
    /// Fires once the product is waiting on the deadline, and when that wait is cancelled.
    let armed = Signal(), cancelled = Signal()
    private let release = AsyncStream<Void>.makeStream()

    func wait(_ duration: Duration) async throws {
        requested.append(duration)
        armed.fire()
        for await _ in release.stream { return }
        cancelled.fire()
        throw CancellationError()
    }
    func fire() { release.continuation.yield() }
}

/// A scripted `/v7/trip-structured` transport: answers in order, counts calls, can hang until cancelled, or hang
/// without looking at cancellation until the test lets it go.
@MainActor private final class ScriptedTripRead {
    enum Step { case respond(LioTimelineHTTP.TripStructuredResponse), fail, hang, hangIgnoringCancellation }
    var steps: [Step]
    private(set) var calls: [String] = []
    private(set) var pauses: [Duration] = []
    private(set) var cancelledReads = 0
    private var held: [CheckedContinuation<Void, Never>] = []
    /// Fires when a read starts waiting, and when a hanging read ends (cancelled, or let go).
    let started = Signal(), ended = Signal()

    init(_ steps: [Step]) { self.steps = steps }

    func read(_ tripID: String) async throws -> LioTimelineHTTP.TripStructuredResponse {
        calls.append(tripID)
        let step = steps.isEmpty ? Step.fail : steps.removeFirst()
        switch step {
        case .respond(let response): return response
        case .fail: throw URLError(.notConnectedToInternet)
        case .hang:
            started.fire()
            defer { ended.fire() }
            do {
                try await Task.sleep(for: .seconds(30))
            } catch {
                cancelledReads += 1
                throw error
            }
            throw URLError(.timedOut)
        case .hangIgnoringCancellation:
            started.fire()
            defer { ended.fire() }
            await withCheckedContinuation { held.append($0) }
            throw URLError(.timedOut)
        }
    }

    /// Lets the reads that ignore cancellation finish.
    func release() {
        let waiting = held
        held = []
        for continuation in waiting { continuation.resume() }
    }

    func places(enabled: Bool = true, timeout: Duration = .seconds(8), deadline: ManualDeadline? = nil) -> LioChatTripPlaces {
        let pause: @Sendable (Duration) async throws -> Void = { duration in await MainActor.run { self.pauses.append(duration) } }
        guard let deadline else {
            return LioChatTripPlaces(enabled: enabled, read: { try await self.read($0) }, timeout: timeout, pause: pause)
        }
        return LioChatTripPlaces(enabled: enabled, read: { try await self.read($0) }, timeout: timeout, pause: pause,
                                 waitForDeadline: { try await deadline.wait($0) })
    }
}

@MainActor struct LioChatTripPlacesTests {
    static let trace = "00000000-0000-4000-8000-000000000001"
    static let tripID = "trip-1"
    static let version: Int64 = 3

    // MARK: Fixtures

    private func content(_ name: String) throws -> [String: Any] {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let data = try Data(contentsOf: root.appendingPathComponent("contracts/trip/structured-examples.4.json"))
        let file = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let cases = try #require(file["cases"] as? [String: [String: Any]])
        return try #require(cases[name]?["content"] as? [String: Any])
    }
    private func canonical(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    }
    /// The content's real hash; a fixed stand-in when the content is deliberately invalid.
    private func hash(_ content: [String: Any]) throws -> String {
        (try? RichStructuredTripDocument.decode(canonical(content)).contentSHA256) ?? String(repeating: "0", count: 64)
    }
    private func body(_ content: [String: Any]?, version: Int64 = version, tripID: String = tripID,
                      hash: String? = nil, extra: [String: Any] = [:]) throws -> Data {
        var trip: Any = NSNull()
        if let content {
            trip = ["trip_id": tripID, "version": version, "content_sha256": try hash ?? self.hash(content), "content": content]
        }
        var root: [String: Any] = ["version": "TRIP-structured-read.3", "request_id": Self.trace, "trip": trip]
        root.merge(extra) { $1 }
        return try canonical(root)
    }
    private func ok(_ data: Data) -> ScriptedTripRead.Step { .respond(.init(status: 200, requestID: Self.trace, bytes: data)) }
    private static let unavailable = ScriptedTripRead.Step.respond(.init(status: 503, requestID: trace, bytes: Data("""
        {"request_id":"\(trace)","error":{"code":"TRIP_UNAVAILABLE","category":"dependency","message_en":"Request unavailable",\
        "message_zh":"请求不可用","outcome":"unknown","recovery":"retry_safe_read"}}
        """.utf8)))
    private static func status(_ code: Int) -> ScriptedTripRead.Step {
        .respond(.init(status: code, requestID: trace, bytes: Data(#"{"request_id":"x","error":{"code":"ACCESS_DENIED","recovery":"do_not_retry"}}"#.utf8)))
    }

    /// The summary a LIO-trip-card.3 for this content gives: names (the item text) and start times only.
    private func summary(_ content: [String: Any]) throws -> LioPlanSummary {
        let items = try #require(content["items"] as? [[String: Any]])
        let days = try #require(content["days"] as? [[String: Any]])
        let calendar = try #require(content["calendar"] as? [String: Any])
        let start = calendar["start_date"] as? String
        return LioPlanSummary(tripID: Self.tripID, tripVersion: Self.version, title: try #require(content["title"] as? String),
                              startDate: start, undated: start == nil, days: try days.map { day in
            let index = try #require(day["day_index"] as? Int)
            return LioPlanSummary.Day(number: index, date: day["date"] as? String, items: try items.compactMap { item in
                let schedule = try #require(item["schedule"] as? [String: [String: Any]])
                guard schedule["start"]?["day_index"] as? Int == index else { return nil }
                let time = (schedule["start"]?["time"] as? [String: Any])?["value"] as? String
                return LioPlanSummary.Item(id: try #require(item["id"] as? String), label: try #require(item["text"] as? String),
                                           startTime: time, endTime: nil, fixed: false)
            })
        })
    }
    private func reference(_ content: [String: Any], hash: String? = nil) throws -> LioChatTripReference {
        LioChatTripReference(tripID: Self.tripID, tripVersion: Self.version, contentSHA256: try hash ?? self.hash(content))
    }
    private func model() -> (LioSavedPlansModel, LioSavedPlans) {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("LioChatTripPlaces-\(UUID().uuidString)")
        let store = LioSavedPlans(directory: directory, isCurrent: { true })
        return (LioSavedPlansModel(store: store), store)
    }
    private func stops(_ plan: LioPlanSummary) -> [String: LioRichItinerary.Stop] {
        Dictionary(uniqueKeysWithValues: plan.itinerary.days.flatMap(\.stops).map { ($0.id, $0) })
    }
    /// Saves through the model as the chat's Save button does, then reads the saved file back.
    private func save(_ read: ScriptedTripRead, content: [String: Any], hash: String? = nil, enabled: Bool = true,
                      timeout: Duration = .seconds(8)) async throws -> (outcome: LioChatTripPlaces.Outcome?, saved: [LioPlanSummary]) {
        let (model, store) = model()
        let outcome = await model.save(try summary(content), reference: try reference(content, hash: hash),
                                       places: read.places(enabled: enabled, timeout: timeout))
        #expect(model.savingTripIDs.isEmpty)
        return (outcome, try store.load())
    }

    // MARK: Strict decoding

    @Test func aMatchingReadConfirmsMatchedPlacesWithAddressAndOriginalGCJ02Point() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([ok(try body(content))])
        let (outcome, saved) = try await save(read, content: content)
        #expect(outcome == .confirmed)
        #expect(read.calls == [Self.tripID])
        let plan = try #require(saved.first)
        #expect(saved.count == 1 && plan.tripID == Self.tripID && plan.tripVersion == Self.version && plan.source == .chat)
        let stops = stops(plan)
        let first = try #require(stops["item-1"])
        #expect(first.kind == .sight)
        #expect(first.place == .init(nameZH: "演示地点1", nameEN: "Demonstration stop 1", address: "合成地址 / Synthetic address",
                                     matched: true, point: .init(latitude: 39.9, longitude: 116.3)))
        #expect(first.place.driverAddress == "合成地址 / Synthetic address" && first.place.mapPoint != nil)
        // The provider's own GCJ-02 digits, not converted (a Decimal-to-Double rounding at most).
        let second = try #require(stops["item-2"]?.place.point)
        #expect(stops["item-2"]?.kind == .meal)
        #expect(abs(second.latitude - 39.900001) < 1e-9 && abs(second.longitude - 116.300001) < 1e-9)
        let unconfirmed = try #require(stops["item-3"])
        #expect(unconfirmed.kind == .sight)
        #expect(unconfirmed.place == .init(nameZH: "演示地点3", nameEN: "Demonstration stop 3", address: nil, matched: false, point: nil))
        #expect(unconfirmed.place.driverAddress == nil && unconfirmed.place.mapPoint == nil)
        // Times and days stay as the card gave them.
        #expect(plan.itinerary.days.map { $0.stops.map(\.time) } == (try summary(content)).itinerary.days.map { $0.stops.map(\.time) })
    }

    @Test func anAllUnconfirmedReadKeepsBothNamesWithoutAddressesOrPoints() async throws {
        let content = try content("unconfirmed")
        let (outcome, saved) = try await save(ScriptedTripRead([ok(try body(content))]), content: content)
        #expect(outcome == .confirmed)
        let plan = try #require(saved.first)
        for stop in plan.itinerary.days.flatMap(\.stops) {
            #expect(!stop.place.matched && stop.place.address == nil && stop.place.point == nil)
            #expect(stop.place.nameZH.hasPrefix("演示地点") && stop.place.nameEN.hasPrefix("Demonstration stop"))
            #expect(stop.kind == .sight || stop.kind == .meal)
        }
    }

    enum Malformed: String, CaseIterable, Sendable {
        case unknownEnvelopeField, unknownPlaceField, missingAddressField, missingTripField, latitudeOutOfRange,
             longitudeOutOfRange, latitudeNotANumber, matchedWithoutCoordinate, oversized, notJSON, wrongTrace, otherTrip
    }

    @Test(arguments: Malformed.allCases)
    func malformedReadsAreRefusedAndTheSummaryIsSaved(_ kind: Malformed) async throws {
        let content = try content("matched")
        var altered = content
        func editFirstPlace(_ edit: (inout [String: Any]) -> Void) throws {
            var items = try #require(altered["items"] as? [[String: Any]])
            var place = try #require(items[0]["place"] as? [String: Any])
            edit(&place)
            items[0]["place"] = place
            altered["items"] = items
        }
        func coordinate(longitude: String, latitude: String) -> [String: Any] {
            ["raw": "\(longitude),\(latitude)", "longitude": longitude, "latitude": latitude, "crs": "GCJ-02"]
        }
        var step: ScriptedTripRead.Step
        switch kind {
        case .unknownEnvelopeField: step = ok(try body(content, extra: ["price": 1]))
        case .unknownPlaceField:
            try editFirstPlace { $0["rating"] = "5" }
            step = ok(try body(altered, hash: try hash(content)))
        case .missingAddressField:
            try editFirstPlace { $0.removeValue(forKey: "address") }
            step = ok(try body(altered, hash: try hash(content)))
        case .missingTripField:
            var root = try #require(JSONSerialization.jsonObject(with: try body(content)) as? [String: Any])
            var trip = try #require(root["trip"] as? [String: Any])
            trip.removeValue(forKey: "content_sha256")
            root["trip"] = trip
            step = ok(try canonical(root))
        case .latitudeOutOfRange:
            try editFirstPlace { $0["coordinate"] = coordinate(longitude: "116.300000", latitude: "95.000000") }
            step = ok(try body(altered, hash: try hash(content)))
        case .longitudeOutOfRange:
            try editFirstPlace { $0["coordinate"] = coordinate(longitude: "181.000000", latitude: "39.900000") }
            step = ok(try body(altered, hash: try hash(content)))
        case .latitudeNotANumber:
            try editFirstPlace { $0["coordinate"] = coordinate(longitude: "116.300000", latitude: "north") }
            step = ok(try body(altered, hash: try hash(content)))
        case .matchedWithoutCoordinate:
            try editFirstPlace { $0["coordinate"] = NSNull() }
            step = ok(try body(altered, hash: try hash(content)))
        case .oversized:
            var data = try body(content)
            data.append(Data(repeating: 0x20, count: LioChatTripPlaces.maximumBytes + 1 - data.count))
            step = ok(data)
        case .notJSON: step = ok(Data("<html>busy</html>".utf8))
        case .wrongTrace: step = .respond(.init(status: 200, requestID: UUID().uuidString, bytes: try body(content)))
        case .otherTrip: step = ok(try body(content, tripID: "trip-2"))
        }
        let (outcome, saved) = try await save(ScriptedTripRead([step]), content: content)
        #expect(outcome == .failed(.invalid))
        #expect(saved == [try summary(content)])
    }

    // MARK: Comparing the read with the card

    @Test func aNewerVersionReplacesTheWholeRecord() async throws {
        let card = try content("matched"), newer = try content("dated")
        let read = ScriptedTripRead([ok(try body(newer, version: Self.version + 1))])
        let (outcome, saved) = try await save(read, content: card)
        #expect(outcome == .replaced)
        let plan = try #require(saved.first)
        #expect(saved.count == 1 && plan.tripVersion == Self.version + 1 && plan.source == .chat)
        // The newer content wholesale: its calendar, themes, kinds, places, legs and lodging.
        #expect(plan.startDate == "2026-12-01" && !plan.undated)
        #expect(plan.itinerary.days.map(\.date) == ["2026-12-01", "2026-12-02"])
        #expect(plan.itinerary.days.allSatisfy { !$0.theme.isEmpty && !$0.area.isEmpty })
        #expect(plan.itinerary.days.reduce(0) { $0 + $1.legs.count } == 6)
        #expect(plan.itinerary.hotels.count == 2 && !plan.itinerary.lodgingArea.isEmpty)
        let stops = stops(plan)
        #expect(stops["item-1"]?.time == "10:00" && stops["item-1"]?.kind == .sight)
        #expect(stops["item-1"]?.place.matched == true && stops["item-1"]?.place.point == .init(latitude: 39.9, longitude: 116.3))
        #expect(stops["item-3"]?.place.matched == false && stops["item-3"]?.place.address == nil)
    }

    @Test func anOlderVersionIsNotUsed() async throws {
        let content = try content("matched")
        let (outcome, saved) = try await save(ScriptedTripRead([ok(try body(content, version: Self.version - 1))]), content: content)
        #expect(outcome == .conflicting)
        #expect(saved == [try summary(content)])
    }

    @Test func theSameVersionWithAnotherHashIsNotUsed() async throws {
        let content = try content("matched")
        let card = String(repeating: "a", count: 64)
        let (outcome, saved) = try await save(ScriptedTripRead([ok(try body(content))]), content: content, hash: card)
        #expect(outcome == .conflicting)
        #expect(saved == [try summary(content)])
        #expect(saved.first?.itinerary.days.flatMap(\.stops).allSatisfy { !$0.place.matched && $0.kind == .unspecified } == true)
    }

    @Test func aNullTripSavesTheSummary() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([ok(try body(nil))])
        let (outcome, saved) = try await save(read, content: content)
        #expect(outcome == .missing)
        #expect(read.calls.count == 1)
        #expect(saved == [try summary(content)])
    }

    // MARK: Failures fall back to the summary save

    @Test func a503IsRetriedWithBackoffThenUsed() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([Self.unavailable, ok(try body(content))])
        let (outcome, saved) = try await save(read, content: content)
        #expect(outcome == .confirmed)
        #expect(read.calls.count == 2 && read.pauses == [.milliseconds(500)])
        #expect(saved.first.map(stops)?["item-1"]?.place.matched == true)
    }

    @Test func retriesStopAfterTwo() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([Self.unavailable, Self.unavailable, Self.unavailable, ok(try body(content))])
        let (outcome, saved) = try await save(read, content: content)
        #expect(outcome == .failed(.unavailable))
        #expect(read.calls.count == 3 && read.pauses == [.milliseconds(500), .seconds(1)])
        #expect(saved == [try summary(content)])
    }

    @Test(arguments: [401, 400, 404, 500])
    func otherStatusesAreNotRetried(_ code: Int) async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([Self.status(code), ok(try body(content))])
        let (outcome, saved) = try await save(read, content: content)
        #expect(outcome == .failed(.status(code)))
        #expect(read.calls.count == 1 && read.pauses.isEmpty)
        #expect(saved == [try summary(content)])
    }

    @Test func aProxy503WithoutTheRetrySafeBodyIsNotRetried() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([.respond(.init(status: 503, requestID: nil, bytes: Data("{}".utf8))), ok(try body(content))])
        let (outcome, _) = try await save(read, content: content)
        #expect(outcome == .failed(.status(503)) && read.calls.count == 1)
    }

    @Test func aNetworkErrorSavesTheSummary() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([.fail])
        let (outcome, saved) = try await save(read, content: content)
        #expect(outcome == .failed(.network) && read.calls.count == 1)
        #expect(saved == [try summary(content)])
    }

    /// The deadline is completed by hand, so this says what happens at the deadline, not how long it took on the
    /// machine that ran it (the whole suite shares one main actor; a wall-clock bound failed on a slow runner).
    @Test(.timeLimit(.minutes(1))) func noAnswerBeforeTheDeadlineSavesTheSummaryPromptly() async throws {
        let content = try content("matched")
        let (model, store) = model()
        let read = ScriptedTripRead([.hang]), deadline = ManualDeadline()
        let places = read.places(deadline: deadline)
        let card = try summary(content), reference = try reference(content)
        async let outcome = model.save(card, reference: reference, places: places)
        await read.started.wait()
        await deadline.armed.wait()
        #expect(model.isSaving(card), "still waiting: the read has not answered and the deadline has not passed")
        #expect(try store.load().isEmpty)
        deadline.fire()
        #expect(await outcome == .failed(.timeout))
        #expect(deadline.requested == [.seconds(8)])
        #expect(!model.isSaving(card))
        #expect(try store.load() == [card], "the summary is saved without waiting for the hanging read")
        // The hanging read was cancelled, not waited for.
        await read.ended.wait()
        #expect(read.cancelledReads == 1 && read.calls.count == 1)
    }

    @Test(.timeLimit(.minutes(1))) func aReadThatIgnoresCancellationDoesNotHoldTheSave() async throws {
        let content = try content("matched")
        let (model, store) = model()
        let read = ScriptedTripRead([.hangIgnoringCancellation]), deadline = ManualDeadline()
        let places = read.places(deadline: deadline)
        let card = try summary(content), reference = try reference(content)
        async let outcome = model.save(card, reference: reference, places: places)
        await read.started.wait()
        await deadline.armed.wait()
        deadline.fire()
        // The save finishes while the read is still stuck: nothing on the save path waits for it.
        #expect(await outcome == .failed(.timeout))
        #expect(try store.load() == [card])
        #expect(!model.isSaving(card))
        read.release()
        await read.ended.wait()
        // Its late end changes nothing.
        #expect(try store.load() == [card] && read.calls.count == 1)
    }

    @Test(.timeLimit(.minutes(1))) func anAnswerBeforeTheDeadlineCancelsTheDeadline() async throws {
        let content = try content("matched")
        let (model, store) = model()
        let read = ScriptedTripRead([ok(try body(content))]), deadline = ManualDeadline()
        let places = read.places(deadline: deadline)
        let outcome = await model.save(try summary(content), reference: try reference(content), places: places)
        #expect(outcome == .confirmed)
        // Waiting on the deadline ends once the answer is used, instead of running on until it passes.
        await deadline.cancelled.wait()
        #expect(try store.load().first.map(stops)?["item-1"]?.place.matched == true)
    }

    @Test func theDefaultDeadlineAndRetriesAreBounded() {
        let places = ScriptedTripRead([]).places()
        #expect(places.timeout == .seconds(8) && places.maximumRetries == 2)
        #expect(LioChatTripPlaces.backoff(0) + LioChatTripPlaces.backoff(1) < .seconds(8))
    }

    // MARK: The flag

    @Test func withTheFlagOffNothingIsReadAndTheSummaryIsSaved() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([ok(try body(content))])
        let (outcome, saved) = try await save(read, content: content, enabled: false)
        #expect(outcome == .notRead)
        #expect(read.calls.isEmpty)
        #expect(saved == [try summary(content)])
    }

    @Test func aReferenceForAnotherVersionReadsNothing() async throws {
        let content = try content("matched")
        let read = ScriptedTripRead([ok(try body(content))])
        let plan = try summary(content)
        let other = LioChatTripReference(tripID: Self.tripID, tripVersion: Self.version + 1, contentSHA256: try hash(content))
        let result = await read.places().plan(for: other, summary: plan)
        #expect(result.outcome == .notRead && result.plan == plan && read.calls.isEmpty)
    }

    @Test func flagIsOffByDefaultAndListedAndOnInTheRelease() throws {
        #expect(LioChatTripPlacesFeature.infoKey == "G2CChatTripPlacesEnabled")
        #expect(LioChatTripPlacesFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "1", true, 1, "$(G2C_CHAT_TRIP_PLACES_ENABLED)"] {
            #expect(!LioChatTripPlacesFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
        #expect(!LioChatTripPlacesFeature.enabledInBuild, "the test bundle sets no flag")
        var ios = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { ios.deleteLastPathComponent() }
        let plist = try String(contentsOf: ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        #expect(plist.contains("<key>G2CChatTripPlacesEnabled</key><string>$(G2C_CHAT_TRIP_PLACES_ENABLED)</string>"))
        let project = try String(contentsOf: ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"), encoding: .utf8)
        #expect(!project.contains("G2C_CHAT_TRIP_PLACES_ENABLED"), "the setting stays unset in the project")
        let manifestURL = ios.deletingLastPathComponent().appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_CHAT_TRIP_PLACES_ENABLED", "plist": "G2CChatTripPlacesEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        // On for the 58.1 TestFlight build (coordinator, under JT's pre-authorisation, 2026-11-28, stop point 6); the setting itself stays unset in the project.
        #expect((try #require(release["on"] as? [String])).contains("G2C_CHAT_TRIP_PLACES_ENABLED"))
    }

    // MARK: Saved copies

    @Test func aConfirmedSaveIsStoredAsV2AndCountsAsSaved() async throws {
        let content = try content("matched")
        let (model, store) = model()
        let card = try summary(content)
        #expect(await model.save(card, reference: try reference(content),
                                 places: ScriptedTripRead([ok(try body(content))]).places()) == .confirmed)
        let file = store.directory.appendingPathComponent(LioSavedPlans.fileName)
        let raw = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
        #expect(raw["version"] as? Int == 2)
        // Reloaded from disk: matched places keep address and point; unconfirmed ones keep names only.
        let reloaded = try #require(try LioSavedPlans(directory: store.directory, isCurrent: { true }).load().first)
        let stops = stops(reloaded)
        #expect(stops["item-1"]?.place.matched == true && stops["item-1"]?.place.address == "合成地址 / Synthetic address")
        #expect(stops["item-1"]?.place.point == .init(latitude: 39.9, longitude: 116.3))
        #expect(stops["item-4"]?.place == .init(nameZH: "演示地点4", nameEN: "Demonstration stop 4", address: nil, matched: false, point: nil))
        #expect(stops["item-4"]?.kind == .meal)
        #expect(!LioTaxiTripPlaces.confirmed(in: [reloaded]).isEmpty)
        // The card's summary is not equal to the confirmed copy, but the trip at this version is saved.
        #expect(!model.isSaved(card) && model.hasSavedCopy(of: card))
    }

    @Test(.timeLimit(.minutes(1))) func aSecondSaveWhileReadingStartsNothing() async throws {
        let content = try content("matched")
        let (model, _) = model()
        let read = ScriptedTripRead([.hang]), deadline = ManualDeadline()
        let places = read.places(deadline: deadline)
        let card = try summary(content), reference = try reference(content)
        async let first = model.save(card, reference: reference, places: places)
        await read.started.wait()
        #expect(model.isSaving(card))
        #expect(await model.save(card, reference: reference, places: places) == nil)
        await deadline.armed.wait()
        deadline.fire()
        #expect(await first == .failed(.timeout))
        #expect(read.calls.count == 1 && !model.isSaving(card))
    }
}
