import Foundation
import CryptoKit
import Observation
import Testing
import OpenAPIRuntime
import HTTPTypes
@testable import CJMemoryClient

private struct HistoryReply: Sendable { let status: Int; let value: Data }
private actor HistoryWire: ClientTransport {
    var calls: [(String, Data, String)] = []
    let handler: @Sendable (String, Data, String) async throws -> HistoryReply
    init(_ handler: @escaping @Sendable (String, Data, String) async throws -> HistoryReply) { self.handler = handler }
    func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws -> (HTTPResponse, HTTPBody?) {
        let data: Data
        if let body { data = try await Data(collecting: body, upTo: 32768) } else { data = Data() }
        calls.append((operationID, data, request.path ?? ""))
        let reply = try await handler(operationID, data, request.path ?? "")
        var response = HTTPResponse(status: .init(code: reply.status))
        response.headerFields[HTTPField.Name("X-Request-ID")!] = trace
        response.headerFields[.cacheControl] = "no-store"; response.headerFields[.contentType] = "application/json"
        return (response, HTTPBody(reply.value))
    }
}
private func historySettingsJSON(conversation: String = "会话e\u{301}", enabled: Bool = false, source: Int64 = 0) -> [String: Any] {
    ["version":"MEMORY-HISTORY@1", "conversation_id":conversation, "generation":"generation", "epoch":0,
     "enabled":enabled, "source_version":source, "withdrawal_epoch":1]
}
private func historyResponse(_ value: Any) throws -> Data {
    try JSONSerialization.data(withJSONObject: ["version":"MEMORY-HISTORY-result@1", "request_id":trace, "result":value], options: [.sortedKeys])
}
private func historyReceiptJSON(_ bytes: Data) throws -> Data {
    let action = try MemoryHistoryAction(raw: bytes)
    var value = historySettingsJSON(conversation: action.conversationID, enabled: action.change == .enable, source: action.sourceVersion + 1)
    value["generation"] = action.generation; value["epoch"] = action.epoch
    value["action_id"] = action.actionID; value["input_sha256"] = digest(bytes)
    return try historyResponse(value)
}
private func historyError(status: Int = 503, code: String = "MEMORY_HISTORY_UNAVAILABLE", recovery: String = "retry_safe_read") throws -> HistoryReply {
    HistoryReply(status: status, value: try JSONSerialization.data(withJSONObject: ["request_id":trace, "error":[
        "code":code,"category":"dependency","outcome":"unknown","message_en":"Unavailable","message_zh":"不可用","recovery":recovery]]))
}
@MainActor private final class HistoryFixture {
    let base = try! Fixture()
    var conversation = "会话e\u{301}"
    var bindingCallback: (() -> Void)?
    var switchCredential = false
    func store(key: (() throws -> SymmetricKey)? = nil) throws -> MemoryHistoryPendingStore {
        try MemoryHistoryPendingStore(directory: base.root, maximumBytes: 100_000, maximumRecords: 100,
            namespace: .init(environment:base.binding.environment,account:base.binding.account,purpose:.localMemoryPendingV1), keyID:base.keyID,
            key:key ?? { [self] in base.secret })
    }
    func client(_ wire: HistoryWire, credentials: MemoryCredentialCallback? = nil) throws -> MemoryHistoryClient {
        MemoryHistoryClient(endpoint:base.endpoint,credentials:credentials ?? { _ in "SYNTHETIC" },
            currentBinding:{ [self] in let callback=bindingCallback;bindingCallback=nil;callback?();return base.current },
            currentConversation:{ [self] in conversation },pendingStore:try store(),interceptedTransport:wire)
    }
    func model(_ client: MemoryHistoryClient) -> MemoryHistoryPresentation {
        let model=MemoryHistoryPresentation(client:client);model.replace(binding:base.binding,conversationID:conversation);return model
    }
    func clean() {
        base.cleanup()
        try? FileManager.default.removeItem(at:base.root.appendingPathExtension("CJMemoryHistoryRejectionsV1"))
    }
}
private actor HistoryBackend {
    var originals: [Data] = []
    var failCurrent = false
    var loseACK = false
    var effective = false
    var version: Int64 = 0
    func set(fail: Bool = false, lose: Bool = false, effective: Bool = false) { failCurrent=fail;loseACK=lose;self.effective=effective }
    func call(_ operation: String, _ bytes: Data, _ path: String) throws -> HistoryReply {
        switch operation {
        case "applyMemoryHistoryActionV1":
            originals.append(bytes);version += 1
            if loseACK { throw URLError(.networkConnectionLost) }
            return HistoryReply(status:200,value:try historyReceiptJSON(bytes))
        case "queryMemoryHistoryReceiptV1":
            return HistoryReply(status:200,value:try originals.first.map(historyReceiptJSON) ?? historyResponse(NSNull()))
        default:
            if failCurrent { return try historyError() }
            return HistoryReply(status:200,value:try historyResponse(historySettingsJSON(enabled:effective,source:version)))
        }
    }
}
@Suite @MainActor struct MemoryHistoryTests {
    @Test func consentKeepsExactSevenKeysUnicodeAndEpochZero() throws {
        let settings = try MemoryHistorySettings(try historyEnvelope(historyResponse(historySettingsJSON()), trace:trace))
        #expect(!settings.enabled && settings.epoch == 0 && settings.sourceVersion == 0)
        let original = try MemoryHistoryPending(change:.enable,settings:settings)
        let value = try #require(JSONSerialization.jsonObject(with:original.originalUTF8) as? [String:Any])
        #expect(Set(value.keys) == ["version","action_id","operation","conversation_id","expected_generation","expected_epoch","expected_source_version"])
        #expect(Data(original.conversationID.utf8) == Data("会话e\u{301}".utf8))
        #expect(!String(describing:original).contains("会话"))
        let receipt = try MemoryHistoryReceipt(historyEnvelope(historyReceiptJSON(original.originalUTF8),trace:trace),original:original)
        #expect(receipt.historical.enabled && receipt.historical.sourceVersion == 1)
    }
    @Test(arguments: ["true","1.0","1e0","-1","9223372036854775808","null"])
    func countersDoNotCoerceOrRound(_ token: String) throws {
        let raw = String(decoding:try historyResponse(historySettingsJSON()),as:UTF8.self).replacingOccurrences(of:"\"epoch\":0",with:"\"epoch\":"+token)
        #expect(throws:(any Error).self) { try MemoryHistorySettings(historyEnvelope(Data(raw.utf8),trace:trace)) }
    }
    @Test func resultMissingExtraDuplicateAndEnabledZeroDoNotBecomeOff() throws {
        let raw = String(decoding:try historyResponse(historySettingsJSON()),as:UTF8.self)
        for invalid in [raw.replacingOccurrences(of:"\"epoch\":0",with:"\"epoch\":0,\"epoch\":0"),
                        raw.replacingOccurrences(of:"\"epoch\":0,",with:""),
                        raw.replacingOccurrences(of:"\"epoch\":0",with:"\"epoch\":0,\"owner\":\"other\""),
                        raw.replacingOccurrences(of:"\"enabled\":false",with:"\"enabled\":true")] {
            #expect(throws:(any Error).self) { try MemoryHistorySettings(historyEnvelope(Data(invalid.utf8),trace:trace)) }
        }
    }
    @Test func frozenConsentExamplesHaveMatchingGrammar() throws {
        var root = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { root.deleteLastPathComponent() }
        let bytes = try Data(contentsOf: root.appendingPathComponent("contracts/memory-jobs/pg-v1-examples.json"))
        let groups = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: [[String:Any]]])
        for value in try #require(groups["positive"]) where value["codec"] as? String == "consent" {
            _ = try MemoryHistoryAction(raw: JSONSerialization.data(withJSONObject: #require(value["value"])))
        }
        for value in try #require(groups["negative"]) where value["codec"] as? String == "consent" {
            let raw = try JSONSerialization.data(withJSONObject: #require(value["value"]))
            #expect(throws: (any Error).self) { try MemoryHistoryAction(raw: raw) }
        }
    }
    @Test func failedPostNeedsFreshSettingsAndRetainsOriginalRejection() async throws {
        let f=HistoryFixture();defer{f.clean()}
        let wire=HistoryWire { op,_,_ in
            if op=="applyMemoryHistoryActionV1" {
                var value=try #require(JSONSerialization.jsonObject(with: historyError(status:409,code:"MEMORY_HISTORY_CONFLICT",recovery:"do_not_retry").value) as? [String:Any])
                var error=try #require(value["error"] as? [String:Any]);error["outcome"]="failed";error["category"]="conflict";value["error"]=error
                return HistoryReply(status:409,value:try JSONSerialization.data(withJSONObject:value))
            }
            if op=="queryMemoryHistoryReceiptV1" { return HistoryReply(status:200,value:try historyResponse(NSNull())) }
            return HistoryReply(status:200,value:try historyResponse(historySettingsJSON()))
        }
        let model=f.model(try f.client(wire))
        await model.perform(try #require(model.prepareRead()));await model.perform(try #require(model.prepareChange(.enable)))
        let original=try #require(model.original)
        #expect(model.state == .conflict && model.settings == nil && !model.canChange)
        await model.perform(try #require(model.prepareRead()));#expect(model.canChange)
        let reopened=f.model(try f.client(wire));await reopened.perform(try #require(reopened.prepareRead()))
        #expect(!reopened.hasUnresolved && reopened.canChange)
        reopened.selectPending(actionID:original.actionID);await reopened.perform(try #require(reopened.prepareQuery()))
        #expect(reopened.state == .conflict && reopened.rejectionStatus == 409 && reopened.settings == nil)
        #expect(try f.store().records().first?.originalUTF8 == original.originalUTF8)
    }
    @Test func unknownErrorCannotBecomeDefiniteRejectionEvenWith409() async throws {
        let f=HistoryFixture();defer{f.clean()}
        let wire=HistoryWire { op,_,_ in
            if op=="applyMemoryHistoryActionV1" { return try historyError(status:409,code:"ACCESS_UNKNOWN",recovery:"do_not_retry") }
            if op=="queryMemoryHistoryReceiptV1" { return HistoryReply(status:200,value:try historyResponse(NSNull())) }
            return HistoryReply(status:200,value:try historyResponse(historySettingsJSON()))
        }
        let model=f.model(try f.client(wire))
        await model.perform(try #require(model.prepareRead()));await model.perform(try #require(model.prepareChange(.enable)))
        #expect(model.state == .unknown && model.rejectionStatus == nil)
        await model.perform(try #require(model.prepareQuery()));#expect(model.state == .unknown && !model.canChange)
        await model.perform(try #require(model.prepareRead()));#expect(model.hasUnresolved && !model.canChange)
        #expect(await wire.calls.filter{$0.0=="applyMemoryHistoryActionV1"}.count == 1)
    }
    @Test func receiptIsHistoricalAndDoesNotInstallCurrentEnabled() async throws {
        let f=HistoryFixture();defer{f.clean()};let backend=HistoryBackend()
        let wire=HistoryWire { try await backend.call($0,$1,$2) },client=try f.client(wire),model=f.model(client)
        await model.perform(try #require(model.prepareRead()))
        #expect(model.settings?.enabled == false && model.canChange)
        await model.perform(try #require(model.prepareChange(.enable)))
        #expect(model.receipt?.historical.enabled == true && model.settings?.enabled == false)
        #expect(model.state == .ready && model.canChange)
        let calls=await wire.calls
        #expect(calls.map(\.0)==["readMemoryHistorySettingsV1","applyMemoryHistoryActionV1","readMemoryHistorySettingsV1"])
        #expect(try f.store().records().count == 1)
    }
    @Test func settingsFailureAfterKnownReceiptIsNotFailedOrUnknownAction() async throws {
        let f=HistoryFixture();defer{f.clean()};let backend=HistoryBackend()
        let wire=HistoryWire { operation,bytes,path in
            let result=try await backend.call(operation,bytes,path)
            if operation=="applyMemoryHistoryActionV1" { await backend.set(fail:true) }
            return result
        }
        let model=f.model(try f.client(wire))
        await model.perform(try #require(model.prepareRead()))
        await model.perform(try #require(model.prepareChange(.enable)))
        #expect(model.receipt?.historical.enabled == true && model.settings == nil)
        #expect(model.state == .unavailable && model.rejectionStatus == nil && !model.canChange)
    }
    @Test func lostACKReopenQueriesOriginalOnlyAndCurrentStateRemainsIndependent() async throws {
        let f=HistoryFixture();defer{f.clean()};let backend=HistoryBackend();await backend.set(lose:true)
        let wire=HistoryWire { try await backend.call($0,$1,$2) }
        let model=f.model(try f.client(wire))
        await model.perform(try #require(model.prepareRead()))
        let work=try #require(model.prepareChange(.enable)),original=try #require(model.original)
        await model.perform(work);await model.perform(work)
        #expect(model.state == .unknown && model.settings == nil && !model.canChange)
        let reopened=f.model(try f.client(wire))
        await reopened.perform(try #require(reopened.prepareRead()))
        #expect(reopened.hasUnresolved && !reopened.canChange && reopened.pendingActions.count == 1)
        reopened.selectPending(actionID:original.actionID)
        await reopened.perform(try #require(reopened.prepareQuery()))
        #expect(reopened.receipt?.inputSHA256 == original.expectedSHA256 && reopened.settings?.enabled == false)
        #expect(reopened.state == .ready && reopened.canChange)
        #expect(await wire.calls.filter{$0.0=="applyMemoryHistoryActionV1"}.count == 1)
        #expect(try f.store().records().first?.originalUTF8 == original.originalUTF8)
    }
    @Test func queuedOldConversationCannotDispatchAndAtomicPublicationKeepsNewSlot() async throws {
        let f=HistoryFixture();defer{f.clean()};let backend=HistoryBackend()
        let wire=HistoryWire { try await backend.call($0,$1,$2) },model=f.model(try f.client(wire))
        await model.perform(try #require(model.prepareRead()))
        withObservationTracking { _=model.state } onChange: {
            MainActor.assumeIsolated { f.conversation="B";model.replace(binding:f.base.binding,conversationID:"B") }
        }
        let stale=try #require(model.prepareChange(.enable));await model.perform(stale)
        #expect(model.conversationID=="B" && model.original==nil && model.settings==nil && model.state == .unread)
        #expect(await wire.calls.count == 1);#expect(try f.store().records().isEmpty)
    }
    @Test func credentialCallbackSwitchBlocksPostAfterOriginalDurability() async throws {
        let f=HistoryFixture();defer{f.clean()};let backend=HistoryBackend()
        let wire=HistoryWire { try await backend.call($0,$1,$2) }
        let client=try f.client(wire,credentials:{_ in if f.switchCredential{f.conversation="B"};return "SYNTHETIC"})
        let model=f.model(client);await model.perform(try #require(model.prepareRead()))
        f.switchCredential=true;await model.perform(try #require(model.prepareChange(.enable)))
        #expect(await wire.calls.filter{$0.0=="applyMemoryHistoryActionV1"}.isEmpty)
        #expect(try f.store().records().count == 1)
        #expect(model.state == .recoveryUnavailable)
    }
}
