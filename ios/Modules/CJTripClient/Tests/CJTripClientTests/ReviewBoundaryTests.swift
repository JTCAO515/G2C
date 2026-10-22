import Foundation
import Testing
@testable import CJTripClient

@Suite @MainActor struct ReviewBoundaryTests {
    @Test func queuedOriginalClickMustNotRetargetNewSelection() async throws {
        let h = try Harness(); defer { h.clean() }
        let store = try h.store(); try store.append(pending()); try store.append(pending(.reject))
        let wire = Interceptor { _, _, _ in "{\"request_id\":\"\(trace)\",\"receipt\":null}" }
        let state = TripPresentation(client: try h.client(wire, store: store)); state.replace(binding: h.binding)
        state.selectPending(actionID: "accept1")
        let original = try #require(state.prepareReconciliation())
        let old = Task { await state.perform(original) }
        state.selectPending(actionID: "reject1")
        await old.value
        #expect(await wire.calls.isEmpty)
        #expect(state.selectedActionID == "reject1")
    }
    @Test func keyCallbackNewSelectionMustWin() throws {
        let h = try Harness(); defer { h.clean() }
        try h.store().append(pending()); try h.store().append(pending(.reject))
        var hook: (() -> Void)?
        let store = try h.store(key: { let f = hook; hook = nil; f?(); return h.key })
        let state = TripPresentation(client: try h.client(Interceptor { _, _, _ in "{}" }, store: store))
        state.replace(binding: h.binding)
        hook = { state.selectPending(actionID: "reject1") }
        state.selectPending(actionID: "accept1")
        #expect(state.selectedActionID == "reject1")
    }
    @Test func finalBindingCallbackDirectoryReplacementMustPreventDispatch() async throws {
        let h = try Harness(); defer { h.clean() }
        let retained = h.root.appendingPathExtension("retained"); defer { try? FileManager.default.removeItem(at: retained) }
        let store = try h.store(); let original = try pending()
        var reads = 0; var hook: (() -> Void)?; var swapped = false
        let wire = Interceptor { _, _, _ in try response("receipt", actionReceipt(original)) }
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in
            reads = 0
            hook = {
                reads += 1
                if reads == 3 {
                    try! FileManager.default.moveItem(at: h.root, to: retained)
                    try! FileManager.default.createDirectory(at: h.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
                    swapped = true
                }
            }
            return "synthetic"
        }, currentBinding: { hook?(); return h.binding }, pendingStore: store, interceptedTransport: wire)
        await #expect(throws: TripFailure.exchangeUnknown) { try await client.submitFixture(original, binding: h.binding, now: 1) }
        #expect(swapped)
        #expect(await wire.calls.isEmpty)
        #expect(try h.store().pending().isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: retained.path).count == 1)
    }
    @Test func queuedDetailUsesOriginalSelectionAndWorkIsOneUse() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in try response("trip", record("B")) }
        let client = try h.client(wire)
        let state = TripPresentation(client: client); state.replace(binding: h.binding)
        let a = try #require(state.prepareTrip(id: "A"))
        let queuedA = Task { await state.perform(a) }
        let b = try #require(state.prepareTrip(id: "B"))
        await queuedA.value
        #expect(await wire.calls.isEmpty)
        await state.perform(b); await state.perform(b)
        #expect(await wire.calls.count == 1)
        #expect(state.trip?.trip_id == "B")
        let other = TripPresentation(client: client); other.replace(binding: h.binding)
        await other.perform(b)
        #expect(await wire.calls.count == 1 && other.trip == nil)
    }
    @Test func queuedNextPageCannotAdoptRefreshedList() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in
            "{\"request_id\":\"\(trace)\",\"trips\":[\(try json(record()))],\"next_after\":\"trip1\"}"
        }
        let state = TripPresentation(client: try h.client(wire)); state.replace(binding: h.binding)
        await state.perform(try #require(state.prepareTrips(limit: 1)))
        let oldPage = try #require(state.prepareTrips(limit: 1, more: true))
        let queued = Task { await state.perform(oldPage) }
        let refresh = try #require(state.prepareTrips(limit: 1))
        await queued.value
        #expect(await wire.calls.count == 1)
        await state.perform(refresh)
        #expect(await wire.calls.count == 2)
        #expect(state.trips.map(\.trip_id) == ["trip1"])
        #expect(await wire.calls.allSatisfy { $0.path?.contains("after=") != true })
    }
    @Test func queuedWorkCannotAdoptNewHostLifetime() async throws {
        let h = try Harness(); defer { h.clean() }
        try h.store().append(pending())
        let wire = Interceptor { _, _, _ in "{}" }
        let state = TripPresentation(client: try h.client(wire)); state.replace(binding: h.binding)
        state.selectPending(actionID: "accept1")
        let original = try #require(state.prepareReconciliation())
        let queued = Task { await state.perform(original) }
        state.replace(binding: h.binding) // Same values, new lifetime.
        await queued.value
        #expect(await wire.calls.isEmpty && state.selectedActionID == nil)
        guard case .unavailable = state.decision else { Issue.record("stale work changed reset UI"); return }
    }
    @Test func keyCallbackFailureCannotClearNewSameBindingSelection() throws {
        let h = try Harness(); defer { h.clean() }
        try h.store().append(pending()); try h.store().append(pending(.reject))
        var hook: (() throws -> Void)?
        let store = try h.store(key: { let f = hook; hook = nil; try f?(); return h.key })
        let state = TripPresentation(client: try h.client(Interceptor { _, _, _ in "{}" }, store: store))
        state.replace(binding: h.binding)
        hook = { state.selectPending(actionID: "reject1"); throw TripFailure.keyUnavailable }
        state.selectPending(actionID: "accept1")
        #expect(state.selectedActionID == "reject1" && state.proposalState == .loaded && state.pendingState == .loaded)
        guard case .unknown = state.decision else { Issue.record("old selection error affected B"); return }
    }
    @Test func lastBindingCallbackCannotDisplaceOnlyOriginalFile() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let store = try h.store()
        let filename = digest(Data(original.actionID.utf8)) + ".trip"
        let retained = h.root.appendingPathExtension("retained-file"); defer { try? FileManager.default.removeItem(at: retained) }
        var reads = 0; var hook: (() -> Void)?; var moved = false
        let wire = Interceptor { _, _, _ in try response("receipt", actionReceipt(original)) }
        let client = TripClient(endpoint: h.endpoint, credentials: { _ in
            hook = {
                reads += 1
                if reads == 3 {
                    try! FileManager.default.moveItem(at: h.root.appendingPathComponent(filename), to: retained)
                    moved = true
                }
            }
            return "synthetic"
        }, currentBinding: { hook?(); return h.binding }, pendingStore: store, interceptedTransport: wire)
        await #expect(throws: TripFailure.exchangeUnknown) { try await client.submitFixture(original, binding: h.binding, now: 1) }
        #expect(moved && FileManager.default.fileExists(atPath: retained.path))
        #expect(await wire.calls.isEmpty)
        #expect(try store.pending().isEmpty)
    }

}
