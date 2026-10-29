import Foundation
import Testing
import CJMessageClient
import CJMessageHTTP
import CJSession
import HTTPTypes
import OpenAPIRuntime
@testable import CJUsageClient

@MainActor private final class ReferenceStorage: SecureMessageStorage {
    var snapshot: Snapshot?
    func load(scope: StorageScope) throws -> Snapshot? { snapshot }
    func save(_ snapshot: Snapshot, scope: StorageScope) throws { self.snapshot = snapshot }
}
@MainActor private final class ReferenceCredentials: MessageCredentialsProvider {
    func bearer(for scope: StorageScope, lease: Lease) async throws -> String? { "synthetic" }
}
@MainActor struct ReferenceFieldControlsTests {
    func row() -> [String: Any] {
        ["message_id":"m", "conversation_id":"c", "generation":"g", "run_id":"r", "message_sequence":1, "attempt_id":"a", "operation_id":"o"]
    }
    @Test(arguments: ["message_id", "conversation_id", "generation", "run_id", "attempt_id", "operation_id"])
    func emptyReferenceStillRejected(_ field: String) {
        var value = row(); value[field] = ""
        #expect(throws: UsageFailure.invalidResponse) { try validateAssociationWire(["request_id":"trace", "association":value]) }
    }
    @Test(arguments: ["attempt_id", "operation_id", "run_id"], [200, 201])
    func usageAndStoredRunBoundRetained(_ field: String, _ length: Int) throws {
        var value = row(); value[field] = String(repeating:"🧭", count:length)
        if length == 200 { try validateAssociationWire(["request_id":"trace", "association":value]) }
        else { #expect(throws: UsageFailure.invalidResponse) { try validateAssociationWire(["request_id":"trace", "association":value]) } }
    }
    /// Actual canonical MESSAGE query forms accepted input before capture. The
    /// unicode MESSAGE reference exceeds BOTH the old 200-scalar and 800-byte caps.
    @Test(arguments: ["message_id", "conversation_id", "generation"])
    func unicodeMessageRefsUseConfiguredBudgetsNotUsageIDLimit(_ field: String) async throws {
        let scope = try StorageScope(environment:"synthetic-ref-" + UUID().uuidString, account:"synthetic")
        let recovery = MessageRecovery(storage:ReferenceStorage()); let lease = try recovery.activate(scope)
        let text = String(repeating:"🧭", count:201)
        let message = field == "message_id" ? text : "m"
        let conversation = field == "conversation_id" ? text : "c"
        let generation = field == "generation" ? text : "g"
        let raw = try JSONSerialization.data(withJSONObject:["version":"MESSAGE-send.1", "message_id":message, "conversation_id":conversation, "text":"synthetic", "trip_id":NSNull(), "creation_intent":"none","expected_generation":generation,"expected_sequence":0])
        try recovery.stage(messageID:message, originalUTF8:raw, lease:lease)
        let submission = try recovery.beginSubmission(messageID:message, lease:lease); try recovery.observeUnknown(submission.operation)
        let staged = try #require(try recovery.action(messageID:message, lease:lease))
        let receipt:[String:Any] = ["message_id":message, "conversation_id":conversation, "generation":generation, "run_id":"r", "sequence":1, "input_sha256":staged.inputSHA256]
        let bytes = try JSONSerialization.data(withJSONObject:receipt)
        let endpoint = try MessageEndpoint(url:URL(string:"https://synthetic.invalid")!, maximumRequestBytes:4096, maximumResponseBytes:16384)
        let http = MessageHTTPClient(recovery:recovery, scope:scope, endpoint:endpoint, credentials:ReferenceCredentials(), interceptedTestTransport:Intercept { _,_,_,operation in
            #expect(operation == "queryMessageReceipt")
            let trace = "00000000-0000-4000-8000-000000000818"
            var response = HTTPResponse(status:.ok); response.headerFields[.contentType] = "application/json"; response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
            return (response, HTTPBody(try JSONSerialization.data(withJSONObject:["request_id":trace, "receipt":receipt])))
        })
        if case .accepted = try await http.query(messageID:message, lease:lease) {} else { Issue.record("canonical input not accepted") }
        let accepted = try #require(try recovery.action(messageID:message, lease:lease))
        let session = SessionLifecycle(persistence:MemorySession(), restorePolicy:.userInitiatedOnly)
        let model = OriginalUsageViewModel(session:session, recovery:recovery, scope:scope, endpoint:endpoint, currentBinding:{ nil })
        let captured = try model.captureAcceptedMessage(accepted, lease:lease)
        #expect(Data(captured.messageID.utf8) == Data(message.utf8))
        var value = row(); value[field] = text
        try validateAssociationWire(["request_id":"trace", "association":value])
        // Capture still respects each explicitly configured total byte budget.
        for capped in [try MessageEndpoint(url:endpoint.url, maximumRequestBytes:raw.count-1, maximumResponseBytes:16384),
                       try MessageEndpoint(url:endpoint.url, maximumRequestBytes:4096, maximumResponseBytes:bytes.count-1)] {
            let bounded = OriginalUsageViewModel(session:session, recovery:recovery, scope:scope, endpoint:capped, currentBinding:{ nil })
            #expect(throws: UsageFailure.unavailable) { try bounded.captureAcceptedMessage(accepted, lease:lease) }
        }
    }
}

@MainActor extension ReferenceFieldControlsTests {
    @Test func associationTransportRetainsExplicitRequestAndResponseByteCaps() async throws {
        let endpoint = try MessageEndpoint(url:URL(string:"https://synthetic.invalid")!, maximumRequestBytes:1024, maximumResponseBytes:1024)
        var association = row(); association["message_id"] = String(repeating:"m", count:2000)
        let trace = "00000000-0000-4000-8000-000000000818"
        let bytes = try JSONSerialization.data(withJSONObject:["request_id":trace, "association":association])
        let transport = UsageTransport(underlying:Intercept { _,_,_,_ in
            var response = HTTPResponse(status:.ok); response.headerFields[.contentType] = "application/json"; response.headerFields[.cacheControl] = "no-store"
            response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
            return (response, HTTPBody(bytes))
        }, endpoint:endpoint, bearer:"synthetic", association:true, validate:{})
        let path = "/v1/message-usage-association?message_id=m"
        let request = HTTPRequest(method:.get, scheme:nil, authority:nil, path:path)
        await #expect(throws:(any Error).self) { try await transport.send(request, body:nil, baseURL:endpoint.url, operationID:"getOriginalUsageAssociation") }
        let oversized = HTTPRequest(method:.get, scheme:nil, authority:nil, path:path + String(repeating:"m", count:1024))
        await #expect(throws:UsageFailure.unavailable) { try await transport.send(oversized, body:nil, baseURL:endpoint.url, operationID:"getOriginalUsageAssociation") }
    }
}
