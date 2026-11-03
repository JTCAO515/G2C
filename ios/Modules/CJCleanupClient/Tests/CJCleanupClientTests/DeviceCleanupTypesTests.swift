import Testing
import Foundation
import CJSession
@testable import CJCleanupClient

private let deviceStateHash = String(repeating: "b", count: 64)
private let deviceSubjectHash = String(repeating: "a", count: 64)
private let deviceTrace = "11111111-1111-4111-8111-111111111450"
private func deviceJSON(_ value: [String: Any]) throws -> Data {
    try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
}
private func enrollmentFixture(query: Bool = false) throws -> DeviceCleanupEnrollment {
    let request = try deviceJSON(["version":"CLEANUP-DEVICE@3", "action_id":"original-action", "device_id":"original-device", "state_ref":deviceStateHash])
    var payload: [String: Any] = ["version":"CLEANUP-DEVICE@3", "binding_id":"original-binding", "device_id":"original-device", "state_ref":deviceStateHash,
        "scope_digest":deviceSubjectHash, "device_token":"SYNTHETIC.DEVICE.CAPABILITY", "server_time":1000, "business_access":"not_granted"]
    let response: Data
    if query {
        response = try deviceJSON(["version":"CLEANUP-DEVICE@3", "request_id":deviceTrace, "action_id":"original-action",
            "input_sha256":deviceCleanupSHA(request), "registration":payload])
    } else { payload["request_id"] = deviceTrace; response = try deviceJSON(payload) }
    return try DeviceCleanupEnrollment(originalUTF8: request, replyUTF8: response, fromQuery: query,
        scope: .init(environment: UUID(), account: UUID(), generation: UUID()))
}
private func invocationFixture(enrollment: DeviceCleanupEnrollment, change: ((inout [String: Any]) -> Void)? = nil) throws -> Data {
    var call: [String: Any] = ["version":"CLEANUP-DEVICE@3", "operation_id":"original-operation", "invocation_id":"original-invocation",
        "binding_id":enrollment.bindingID, "scope_digest":enrollment.scopeDigest, "state_ref":enrollment.stateRef,
        "reason":"session_invalid", "targets":DeviceCleanupTarget.allCases.map(\.rawValue), "business_access":"not_granted"]
    change?(&call)
    let digest = deviceCleanupSHA(try deviceJSON(call))
    return try deviceJSON(["call":call, "request_digest":digest, "state":"pending", "receipt_digest":NSNull(), "receipt_token":"SYNTHETIC.RECEIPT.CAPABILITY"])
}
@Test func actualCanonicalPythonCallDigestAndSealedProjectionMatch() throws {
    let enrollment = try enrollmentFixture()
    let wire = try invocationFixture(enrollment: enrollment)
    let invocation = try DeviceCleanupInvocation(result: accountCleanupDocument(wire), enrollment: enrollment, directQuery: false)
    // Independent Python core.encode-compatible public vector, not derived by
    // this Swift parser or a fixture masquerading as an actual server operation.
    #expect(invocation.requestDigest == "c8d309a81a34bca05d46cadb6191b95c8e1678571bf4e4ce703a7b0eeec3ad75")
    #expect(invocation.targets.count == 19 && invocation.operationID == "original-operation")
    #expect(invocation.state == .pending && invocation.receiptDigest == nil)
    #expect(!String(reflecting: invocation).contains("SYNTHETIC"))
    #expect(Mirror(reflecting: invocation).children.isEmpty)
    #expect(!String(reflecting: enrollment).contains("SYNTHETIC"))
    #expect(Mirror(reflecting: enrollment).children.isEmpty)
}
@Test func originalActionHashQueryRecoversOnlyExactEnrollment() throws {
    let enrollment = try enrollmentFixture(query: true)
    #expect(enrollment.bindingID == "original-binding" && enrollment.replyFromQuery)
    var root = try #require(JSONSerialization.jsonObject(with: enrollment.replyUTF8) as? [String: Any])
    root["input_sha256"] = String(repeating: "0", count: 64)
    #expect(throws: CleanupFailure.invalidResponse) {
        try DeviceCleanupEnrollment(originalUTF8: enrollment.originalUTF8, replyUTF8: deviceJSON(root), fromQuery: true, scope: enrollment.scope)
    }
    root["input_sha256"] = deviceCleanupSHA(enrollment.originalUTF8); root["action_id"] = "another-action"
    #expect(throws: CleanupFailure.invalidResponse) {
        try DeviceCleanupEnrollment(originalUTF8: enrollment.originalUTF8, replyUTF8: deviceJSON(root), fromQuery: true, scope: enrollment.scope)
    }
}
@Test(arguments: ["binding", "scope", "state-ref", "version", "grant", "target", "duplicate", "missing"])
func crossScopeOrChangedTargetDoesNotAuthorizeNativeDispatch(change: String) throws {
    let enrollment = try enrollmentFixture()
    let wire = try invocationFixture(enrollment: enrollment) { call in
        switch change {
        case "binding": call["binding_id"] = "other-binding"
        case "scope": call["scope_digest"] = String(repeating: "0", count: 64)
        case "state-ref": call["state_ref"] = String(repeating: "0", count: 64)
        case "version": call["version"] = "CLEANUP-DEVICE@2"
        case "grant": call["business_access"] = "granted"
        case "target": call["targets"] = ["device-cache/unknown-directory"]
        case "duplicate": call["targets"] = DeviceCleanupTarget.allCases.map(\.rawValue) + [DeviceCleanupTarget.offlineTrip.rawValue]
        default: call["targets"] = Array(DeviceCleanupTarget.allCases.dropLast()).map(\.rawValue)
        }
    }
    #expect(throws: CleanupFailure.invalidResponse) {
        try DeviceCleanupInvocation(result: accountCleanupDocument(wire), enrollment: enrollment, directQuery: false)
    }
}
@Test func changedServerDigestAndWrongOriginalOperationReject() throws {
    let enrollment = try enrollmentFixture(), raw = try invocationFixture(enrollment: enrollment)
    var root = try #require(JSONSerialization.jsonObject(with: raw) as? [String: Any])
    root["request_digest"] = String(repeating: "0", count: 64)
    #expect(throws: CleanupFailure.invalidResponse) { try DeviceCleanupInvocation(result: accountCleanupDocument(deviceJSON(root)), enrollment: enrollment, directQuery: false) }
    #expect(throws: CleanupFailure.invalidResponse) { try DeviceCleanupInvocation(result: accountCleanupDocument(raw), enrollment: enrollment, directQuery: false, expectedOperationID: "invented-operation") }
}
@Test func offlineExpiryOnlyPermitsExactThreeOfflineTargetsAndNeverGrantsReads() throws {
    let enrollment = try enrollmentFixture()
    let raw = try invocationFixture(enrollment: enrollment) { call in
        call["reason"] = "offline_expired"
        call["targets"] = [DeviceCleanupTarget.offlineTrip.rawValue, DeviceCleanupTarget.offlineWriteResidue.rawValue, DeviceCleanupTarget.offlineKey.rawValue]
    }
    let invocation = try DeviceCleanupInvocation(result: accountCleanupDocument(raw), enrollment: enrollment, directQuery: false)
    #expect(invocation.reason == .offlineExpired && Set(invocation.targets) == [.offlineTrip, .offlineWriteResidue, .offlineKey])
    let bad = try invocationFixture(enrollment: enrollment) { $0["reason"] = "offline_expired" }
    #expect(throws: CleanupFailure.invalidResponse) { try DeviceCleanupInvocation(result: accountCleanupDocument(bad), enrollment: enrollment, directQuery: false) }
}

@MainActor private final class DeviceJournalMemory: SessionPersistence {
    var value: SessionMaterial?
    var onSave: (() -> Void)?
    func load() throws -> SessionMaterial? { value }
    func save(_ material: SessionMaterial) throws { value = material; let callback = onSave; onSave = nil; callback?() }
    func clearAndBlock() throws { value = nil }
}
@MainActor @Test func secureDeviceJournalReopensExactEnrollmentAndRefusesAnotherAccount() throws {
    let enrollment = try enrollmentFixture(query: true), persistence = DeviceJournalMemory()
    let journal = try DeviceCleanupJournal(persistence: persistence, scope: enrollment.scope)
    var record = journal.record; record.registration = enrollment.originalUTF8; record.enrollmentReply = enrollment.replyUTF8; record.enrollmentFromQuery = true
    try journal.save(record, validate: {})
    let originalBytes = journal.bytes
    let reopened = try DeviceCleanupJournal(persistence: persistence, scope: .init(environment: enrollment.scope.environment, account: enrollment.scope.account, generation: UUID()))
    #expect(reopened.bytes == originalBytes)
    #expect(try reopened.record.enrollment().originalUTF8 == enrollment.originalUTF8)
    #expect(reopened.record.scope.generation == enrollment.scope.generation)
    #expect(throws: CleanupFailure.invalidResponse) {
        try DeviceCleanupJournal(persistence: persistence, scope: .init(environment: enrollment.scope.environment, account: UUID(), generation: UUID()))
    }
}
@MainActor @Test func secureDeviceJournalCallbackRetirementCannotPublishOrDispatch() throws {
    let enrollment = try enrollmentFixture(), persistence = DeviceJournalMemory()
    let journal = try DeviceCleanupJournal(persistence: persistence, scope: enrollment.scope)
    var record = journal.record; record.registration = enrollment.originalUTF8
    var active = true; persistence.onSave = { active = false }
    #expect(throws: CleanupFailure.stale) {
        try journal.save(record) { guard active else { throw CleanupFailure.stale } }
    }
    #expect(journal.bytes == nil)
    #expect(throws: CleanupFailure.stale) { try journal.requireOriginal(nil) }
    // The original durable intent can be recovered, but no server result or
    // replacement action has been manufactured by the interrupted save.
    let restored = try DeviceCleanupJournal(persistence: persistence, scope: enrollment.scope)
    #expect(restored.record.registration == enrollment.originalUTF8)
    #expect(restored.record.enrollmentReply == nil)
}
