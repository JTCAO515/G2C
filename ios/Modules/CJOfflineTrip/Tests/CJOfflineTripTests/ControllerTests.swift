import Foundation
import Observation
import Testing
import CJSession
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes
@testable import CJTripClient
@testable import CJOfflineTrip

@MainActor private final class AnchorMemory: SessionPersistence {
    var value: SessionMaterial?
    var blocked = false
    var onSave: (() throws -> Void)?
    func load() throws -> SessionMaterial? {
        if blocked { throw SessionFailure.restorationBlocked }; return value
    }
    func save(_ material: SessionMaterial) throws { try onSave?(); value = material; blocked = false }
    func clearAndBlock() throws { value = nil; blocked = true }
}
@MainActor private final class ControllerClock {
    var wall: Int64 = 1_800_000_000
    var uptime: Double = 10
    var boot = UUID()
    var trusted = true
    func read() -> OfflineClock? {
        .init(trustedWallSeconds: trusted ? wall : nil, boot: boot, uptime: uptime)
    }
}
private actor ControllerWire: ClientTransport {
    let bytes: Data
    init(_ bytes: Data) { self.bytes = bytes }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        #expect(request.method == .get && ["getTrip", "readStructuredTripV1"].contains(operationID))
        let object = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        var response = HTTPResponse(status: .ok)
        response.headerFields[.contentType] = "application/json"
        response.headerFields[.cacheControl] = "no-store"
        response.headerFields[HTTPField.Name("X-Request-ID")!] = try #require(object["request_id"] as? String)
        return (response, HTTPBody(bytes))
    }
}

@Suite @MainActor struct ControllerTests {
    private func client(_ h: KeyHarness) throws -> (TripClient, TripBinding) {
        let binding = TripBinding(environment: h.ns.backend, account: h.ns.account, generation: UUID(), selection: UUID())
        let endpoint = try MessageEndpoint(url: URL(string: "https://offline-unit.invalid")!, maximumRequestBytes: 100_000, maximumResponseBytes: 100_000)
        return (TripClient(endpoint: endpoint, credentials: { _ in "synthetic-unit-only" }, currentBinding: { binding },
            session: h.session, sessionOperation: h.operation, interceptedTransport: ControllerWire(try h.snapshot().responseBytes)), binding)
    }
    private func source(_ client: TripClient, _ binding: TripBinding) async throws -> AcceptedTripDetailSnapshot {
        try #require(try await client.detailSnapshot(for: client.prepareDetailSnapshot(id: "trip1", binding: binding)))
    }
    private func controller(_ h: KeyHarness, _ anchors: AnchorMemory, _ clock: ControllerClock,
                            sdk: AnchorMemory, policy: OfflinePolicy? = .acceptedTrip) throws -> OfflineTripController {
        let value = OfflineTripController(environment: h.ns.backend, root: h.root, anchors: anchors, sdkMaterial: sdk.load,
            makeKeys: { _ in h.provider }, clock: clock.read, policy: policy)
        if let material = sdk.value {
            try value.bindSynchronizationIdentity(material: material, account: h.ns.account, session: h.session, operation: h.operation)
        }
        return value
    }
    @Test func acceptedSyncReopenExpiryClockRollbackAndFreshSync() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
        let (client, binding) = try client(h)
        let first = try controller(h, anchors, clock, sdk: sdk)
        let accepted = try await source(client, binding)
        try first.synchronize(client: client, source: accepted, session: h.session, operation: h.operation)
        let originalAnchor = try #require(anchors.value).withBytes { $0 }
        #expect(throws: OfflineFailure.unavailable) {
            try first.synchronize(client: client, source: accepted, session: h.session, operation: h.operation)
        }
        #expect(try anchors.value?.withBytes({ $0 }) == originalAnchor)
        let reopened = try controller(h, anchors, clock, sdk: sdk)
        reopened.readCached()
        guard case .readable(let value) = reopened.state else { Issue.record("Expected original encrypted cache"); return }
        #expect(value.namespace == h.ns && value.version == 2 && value.deadline == clock.wall + 1_209_600)
        if case .text(let trip) = value.content { #expect(trip.document.title == "北京 Beijing") }
        else { Issue.record("Wrong format") }
        clock.wall -= 1
        reopened.checkDisplayedTime()
        guard case .untrustedTime = reopened.state else { Issue.record("Rollback must deny"); return }
        clock.wall = value.deadline; clock.uptime += 1_209_600
        reopened.readCached()
        guard case .expired = reopened.state else { Issue.record("Deadline equality must deny"); return }
        let fresh = try await source(client, binding)
        try reopened.synchronize(client: client, source: fresh, session: h.session, operation: h.operation)
        reopened.readCached()
        guard case .readable(let renewed) = reopened.state else { Issue.record("New actual GET must renew"); return }
        #expect(renewed.syncedAt == value.deadline && renewed.deadline == value.deadline + 1_209_600)
    }
    @Test func missingPolicyUntrustedBootAndChangedSDKCannotRead() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
        let (client, binding) = try client(h)
        let active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
        let denied = try controller(h, anchors, clock, sdk: sdk, policy: nil)
        denied.readCached()
        guard case .unavailable = denied.state else { Issue.record("Missing policy must deny"); return }
        clock.boot = UUID(); active.readCached()
        guard case .untrustedTime = active.state else { Issue.record("New boot must deny until online sync"); return }
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-b".utf8)))
        active.readCached()
        guard case .unavailable = active.state else { Issue.record("SDK account change must deny"); return }
    }
    @Test func localClearDurablyDeniesBeforeRemovingExactFile() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
        let (client, binding) = try client(h)
        let active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
        let file = h.root.appendingPathComponent(h.ns.account.uuidString).appendingPathComponent("snapshot.aesgcm")
        #expect(FileManager.default.fileExists(atPath: file.path))
        try active.clearLocally()
        #expect(!FileManager.default.fileExists(atPath: file.path))
        let reopened = try controller(h, anchors, clock, sdk: sdk)
        reopened.readCached()
        guard case .missing = reopened.state else { Issue.record("Cleared grant must remain absent"); return }
    }
    @Test func deviceHookBindsExactAccountAndClearsOriginalResidueWithoutKeyReplacement() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-device-original".utf8)))
        let (client, binding) = try client(h), active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
        let directory = h.root.appendingPathComponent(h.ns.account.uuidString)
        let snapshot = directory.appendingPathComponent("snapshot.aesgcm")
        let bytes = try Data(contentsOf: snapshot), original = anchors.value?.withBytes { $0 }
        #expect(throws: OfflineFailure.wrongNamespace) { try active.clearDeviceAccount(account: UUID()) }
        #expect(throws: OfflineFailure.wrongNamespace) { try active.clearDeviceTemporaryWrites(account: UUID()) }
        #expect(try Data(contentsOf: snapshot) == bytes && anchors.value?.withBytes { $0 } == original)
        let temporary = directory.appendingPathComponent(".write-" + UUID().uuidString)
        try Data([1,2,3]).write(to: temporary)
        try active.clearDeviceAccount(account: h.ns.account)
        try active.verifyDeviceAnchorCleared()
        #expect(!FileManager.default.fileExists(atPath: snapshot.path))
        #expect(FileManager.default.fileExists(atPath: temporary.path))
        try active.clearDeviceTemporaryWrites(account: h.ns.account)
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty)
        let retained = try h.provider.existing(expectedID: h.expectedID, for: h.provider.begin(.lookup))
        #expect(retained?.id == h.expectedID)
    }
    @Test func exactOrphanWithoutAnchorIsErasedButNeverRestoredReadable() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-device-original".utf8)))
        let (client, binding) = try client(h), active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
        anchors.value = nil // Interruption lost the grant; the protected exact file is not a read source.
        let reopened = try controller(h, anchors, clock, sdk: sdk)
        reopened.readCached(); guard case .missing = reopened.state else { Issue.record("Orphan became readable"); return }
        try reopened.clearDeviceAccount(account: h.ns.account)
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.appendingPathComponent(h.ns.account.uuidString).path).isEmpty)
        try reopened.verifyDeviceAnchorCleared()
    }
    @Test func wrongRejectedIdentityDoesNotEraseTheCurrentGrant() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
        let (client, binding) = try client(h)
        let active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
        try active.identityRejected(material: SessionMaterial(trustedSDKBytes: Data("other-sdk".utf8)))
        active.readCached()
        guard case .readable = active.state else { Issue.record("Wrong identity erased current grant"); return }
        try active.identityRejected(material: try #require(try sdk.load()))
        #expect(anchors.blocked)
    }
    @Test func observationReentryAndKeyLookupClearCannotPublishOldContent() async throws {
        for duringSave in [false, true] {
            let h = try KeyHarness(); defer { h.cleanup() }
            let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
            try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
            let (client, binding) = try client(h)
            let active = try controller(h, anchors, clock, sdk: sdk)
            try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
            if duringSave {
                var acted = false
                anchors.onSave = {
                    anchors.onSave = nil
                    withObservationTracking { _ = active.state } onChange: {
                        MainActor.assumeIsolated {
                            if acted {
                                #expect(throws: OfflineFailure.unavailable) { try active.clearLocally() }
                            } else {
                                acted = true
                                do { try active.clearLocally() } catch { Issue.record(error) }
                            }
                        }
                    }
                }
            } else {
                h.storage.onRead = {
                    h.storage.onRead = nil
                    try active.clearLocally()
                }
            }
            active.readCached()
            guard case .unavailable = active.state else { Issue.record("Retired content must never publish"); return }
            #expect(anchors.blocked)
            let reopened = try controller(h, anchors, clock, sdk: sdk)
            reopened.readCached()
            guard case .missing = reopened.state else { Issue.record("Retirement must survive reopen"); return }
        }
    }
    @Test func missingKeyNeverRecreatesOrRenewsExistingSnapshot() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
        let (client, binding) = try client(h), active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
        let original = try #require(anchors.value).withBytes { $0 }
        h.storage.value = nil; active.readCached()
        guard case .storageFailure = active.state else { Issue.record("Missing key must deny"); return }
        #expect(h.storage.adds == 0 && h.storage.removes == 0)
        #expect(try anchors.value?.withBytes({ $0 }) == original)
    }

    @Test func structuredAcceptedSourcePreservesOriginalBytesAndReadOnlyDocument() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
        let unknown: [String: Any] = ["state": "unknown"]
        let event: [String: Any] = ["date": unknown, "time": unknown, "timezone": unknown, "utc_offset": unknown]
        let document: [String: Any] = ["content_version": "structured.1", "title": "北京正式行程",
            "items": [["id": "item1", "text": "天坛", "verification": "pending", "evidence": [],
                "schedule": ["start": event, "end": event], "fixed": unknown, "source_category": "unknown", "source_refs": []]], "sources": []]
        let content = try JSONSerialization.data(withJSONObject: document, options: [.sortedKeys, .withoutEscapingSlashes])
        let raw = try JSONSerialization.data(withJSONObject: ["version": "TRIP-structured-read.1", "request_id": UUID().uuidString,
            "trip": ["trip_id": "trip1", "version": 2, "content_sha256": CJOfflineTrip.digest(content), "content": document]], options: [.sortedKeys, .withoutEscapingSlashes])
        let binding = TripBinding(environment: h.ns.backend, account: h.ns.account, generation: UUID(), selection: UUID())
        let endpoint = try MessageEndpoint(url: URL(string: "https://offline-unit.invalid")!, maximumRequestBytes: 100_000, maximumResponseBytes: 100_000)
        let client = TripClient(endpoint: endpoint, credentials: { _ in "synthetic-unit-only" }, currentBinding: { binding },
            session: h.session, sessionOperation: h.operation, interceptedTransport: ControllerWire(raw))
        let request = try client.prepareStructuredDetail(id: "trip1", binding: binding)
        let source = try #require(try await client.structuredDetail(for: request))
        let active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: source, session: h.session, operation: h.operation)
        active.readCached()
        guard case .readable(let read) = active.state, case .structured(let trip) = read.content else {
            Issue.record("Structured source must round-trip"); return
        }
        #expect(read.responseHash == CJOfflineTrip.digest(raw) && trip.document.originalUTF8 == content)
        #expect(trip.document.items[0].text == "天坛" && trip.tripID == "trip1")
    }

    @Test func unconfirmedFirstWriteRetainsDeniedCleanupTargetAcrossReopen() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        let material = try SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8))
        try sdk.save(material)
        let (client, binding) = try client(h)
        var original: OfflineTripController? = OfflineTripController(environment: h.ns.backend, root: h.root,
            anchors: anchors, sdkMaterial: sdk.load, makeKeys: { _ in h.provider }, clock: clock.read, policy: .acceptedTrip,
            makeStore: { directory in
                let store = try AtomicSnapshotStore(existingPrivateDirectory: directory)
                store.afterRename = { throw OfflineFailure.storageFailure }
                return store
            })
        do {
            let active = try #require(original)
            try active.bindSynchronizationIdentity(material: material, account: h.ns.account, session: h.session, operation: h.operation)
            let accepted = try await source(client, binding)
            #expect(throws: OfflineFailure.writeUnknown) {
                try active.synchronize(client: client, source: accepted, session: h.session, operation: h.operation)
            }
            guard case .unknown = active.syncState else { Issue.record("Local uncertainty must remain UNKNOWN"); return }
            #expect(throws: OfflineFailure.writeUnknown) { try active.clearLocally() }
            let deniedBytes = try #require(anchors.value).withBytes { $0 }
            let denied = try JSONDecoder().decode(OfflineAnchor.self, from: deniedBytes)
            #expect(!denied.readAllowed && denied.namespace == h.ns)
        }
        original = nil
        let reopened = try controller(h, anchors, clock, sdk: sdk)
        reopened.readCached()
        guard case .unavailable = reopened.state else { Issue.record("Unconfirmed file cannot become a readable grant"); return }
        try reopened.clearLocally()
        let file = h.root.appendingPathComponent(h.ns.account.uuidString).appendingPathComponent("snapshot.aesgcm")
        #expect(!FileManager.default.fileExists(atPath: file.path) && anchors.blocked)
    }

    @Test func sdkMaterialChangedByKeyLookupCannotPublishOrRenew() async throws {
        let h = try KeyHarness(); defer { h.cleanup() }
        let anchors = AnchorMemory(), sdk = AnchorMemory(), clock = ControllerClock()
        try sdk.save(SessionMaterial(trustedSDKBytes: Data("verified-sdk-unit-a".utf8)))
        let (client, binding) = try client(h), active = try controller(h, anchors, clock, sdk: sdk)
        try active.synchronize(client: client, source: await source(client, binding), session: h.session, operation: h.operation)
        let original = try #require(anchors.value).withBytes { $0 }
        h.storage.onRead = {
            h.storage.onRead = nil
            try sdk.save(SessionMaterial(trustedSDKBytes: Data("different-sdk-material".utf8)))
        }
        clock.wall += 1; clock.uptime += 1
        active.readCached()
        guard case .unavailable = active.state else { Issue.record("Old SDK material must not publish"); return }
        #expect(try anchors.value?.withBytes({ $0 }) == original)
    }

}
