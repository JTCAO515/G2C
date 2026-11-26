import Testing
import Foundation
import CryptoKit
import CJAPI
import CJMessageKeys
@testable import CJFeedbackClient

/// #1855: a confirmed line is removed from the device only after its receipt matched; a line the server has no
/// record of can be sent again once per "no such line" answer, under its own ID and exact bytes; the cap rolls.
@MainActor struct ResendAndCleanupTests {
    private func receiptEcho() -> Interceptor {
        Interceptor { _, bytes, operation in
            let action = try JSONDecoder().decode(Components.Schemas.FeedbackAction.self, from: bytes)
            let original = try FeedbackPending(problem: action.problem, expectation: action.expectation, context: nil, actionID: action.action_id)
            return Reply(text: try receiptJSON(original))
        }
    }

    // MARK: removal only after a verified receipt

    @Test func badReceiptsNeverRemoveTheRecord() async throws {
        for kind in ["hash", "action", "garbage"] {
            let h = try Harness(); defer { h.clean() }
            let original = try pending(); let store = try h.store(); try store.append(original)
            var body = try receiptJSON(original)
            switch kind {
            case "hash": body = body.replacingOccurrences(of: original.inputSHA256, with: String(repeating: "0", count: 64))
            case "action": body = body.replacingOccurrences(of: original.actionID, with: "different")
            default: body = "{"
            }
            let final = body
            let client = try h.client(Interceptor { _, _, _ in Reply(text: final) }, store: store)
            let op = try client.begin(binding: h.binding)
            await #expect(throws: (any Error).self) { try await client.queryOriginal(actionID: original.actionID, operation: op) }
            #expect(try store.pending().map(\.actionID) == [original.actionID], "no receipt, no removal (\(kind))")
        }
    }

    @Test func failedSubmitsAndUnknownResultsKeepTheRecord() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let store = try h.store()
        let client = try h.client(Interceptor { _, _, _ in throw URLError(.networkConnectionLost) }, store: store)
        let op = try client.begin(binding: h.binding)
        await #expect(throws: FeedbackFailure.exchangeUnknown) { try await client.submit(original, operation: op) }
        #expect(try store.pending().map(\.actionID) == [original.actionID])
        let refused = try h.client(Interceptor { _, _, _ in Reply(text: "{}", status: 409) }, store: store)
        await #expect(throws: (any Error).self) { try await refused.queryOriginal(actionID: original.actionID, operation: refused.begin(binding: h.binding)) }
        #expect(try store.pending().map(\.actionID) == [original.actionID], "a conflict is not a receipt")
    }

    @Test func removalFailureKeepsTheConclusionAndTheNextLaunchCleansWithoutResending() async throws {
        let h = try Harness(); defer { try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: h.root.path); h.clean() }
        let original = try pending(); let store = try h.store(); try store.append(original)
        let first = try h.client(Interceptor { _, _, _ in Reply(text: try receiptJSON(original)) }, store: store)
        let op = try first.begin(binding: h.binding)
        // The folder cannot be written to: the record cannot be removed.
        try FileManager.default.setAttributes([.posixPermissions: 0o500], ofItemAtPath: h.root.path)
        guard case .submitted = try await first.queryOriginal(actionID: original.actionID, operation: op) else { Issue.record("receipt lost"); return }
        #expect(try store.pending().map(\.actionID) == [original.actionID], "removal failed, record stays")
        // Same session: it is confirmed, so new feedback is not blocked and the line is never sent again.
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await first.submit(original, operation: op) }
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: h.root.path)
        // Next launch: the record is looked up (query only), settled again and removed. Nothing is sent.
        let wire = Interceptor { _, _, _ in Reply(text: try receiptJSON(original)) }
        let reopened = try h.client(wire, store: store); let next = try reopened.begin(binding: h.binding)
        guard case .submitted = try await reopened.queryOriginal(actionID: original.actionID, operation: next) else { Issue.record("no receipt"); return }
        #expect(await wire.calls.map(\.operation) == ["queryFeedbackAction"])
        #expect(try store.pending().isEmpty)
    }

    @Test func aConfirmedLineIsNeverSubmittedAgainInThisSession() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let wire = receiptEcho(); let client = try h.client(wire)
        let op = try client.begin(binding: h.binding)
        _ = try await client.submit(original, operation: op)
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(original, operation: op) }
        let sameIDOtherBytes = try FeedbackPending(problem: "Other words", expectation: "", context: nil, actionID: original.actionID)
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(sameIDOtherBytes, operation: op) }
        #expect(await wire.calls.count == 1)
    }

    // MARK: rolling cap

    @Test func confirmedLinesDoNotCountTowardsTheCapButUnconfirmedOnesDo() async throws {
        let h = try Harness(); defer { h.clean() }
        let store = try FeedbackPendingStore(directory: h.root, maximumBytes: 100_000, maximumRecords: 2, namespace: h.namespace, keyID: h.keyID) { h.key }
        let client = try h.client(receiptEcho(), store: store); let op = try client.begin(binding: h.binding)
        for index in 0..<5 {
            guard case .submitted = try await client.submit(pending(actionID: "line-\(index)"), operation: op) else { Issue.record("line \(index)"); return }
        }
        #expect(try store.pending().isEmpty, "five lines through a cap of two")
        try store.append(pending(actionID: "open-1")); try store.append(pending(actionID: "open-2"))
        #expect(throws: FeedbackFailure.storageUnavailable) { try store.append(pending(actionID: "open-3")) }
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(pending(actionID: "open-3"), operation: op) }
        #expect(try store.pending().count == 2)
    }

    // MARK: resend under the original ID

    @Test func aLineTheServerHasNoRecordOfIsSentAgainOnceUnderItsOwnIDAndBytes() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(linked: false); let store = try h.store(); try store.append(original)
        let wire = Interceptor { _, _, operation in
            operation == "queryFeedbackAction" ? Reply(text: nullResponse) : Reply(text: try receiptJSON(original))
        }
        let client = try h.client(wire, store: store); let op = try client.begin(binding: h.binding)
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.resend(actionID: original.actionID, operation: op) }
        #expect(await wire.calls.isEmpty, "no look-up answered yet, so nothing goes out")
        guard case .notObserved = try await client.queryOriginal(actionID: original.actionID, operation: op) else { Issue.record("expected none"); return }
        #expect(client.canResend(actionID: original.actionID))
        guard case .submitted = try await client.resend(actionID: original.actionID, operation: op) else { Issue.record("no receipt"); return }
        let calls = await wire.calls
        #expect(calls.map(\.operation) == ["queryFeedbackAction", "submitFeedback"])
        #expect(calls[1].bytes == original.originalUTF8, "same ID, same bytes")
        #expect(try store.pending().isEmpty)
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.resend(actionID: original.actionID, operation: op) }
    }

    @Test func oneResendPerNoSuchLineAnswerEvenWhenItsOwnOutcomeIsUnknown() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let store = try h.store(); try store.append(original)
        let wire = Interceptor { _, _, operation in
            if operation == "queryFeedbackAction" { return Reply(text: nullResponse) }
            throw URLError(.networkConnectionLost)
        }
        let client = try h.client(wire, store: store); let op = try client.begin(binding: h.binding)
        _ = try await client.queryOriginal(actionID: original.actionID, operation: op)
        await #expect(throws: FeedbackFailure.exchangeUnknown) { try await client.resend(actionID: original.actionID, operation: op) }
        #expect(!client.canResend(actionID: original.actionID))
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.resend(actionID: original.actionID, operation: op) }
        #expect(await wire.calls.filter { $0.operation == "submitFeedback" }.count == 1)
        // Only another "no such line" answer earns another resend; the record and its ID never change.
        _ = try await client.queryOriginal(actionID: original.actionID, operation: op)
        await #expect(throws: FeedbackFailure.exchangeUnknown) { try await client.resend(actionID: original.actionID, operation: op) }
        let submits = await wire.calls.filter { $0.operation == "submitFeedback" }
        #expect(submits.count == 2 && submits.allSatisfy { $0.bytes == original.originalUTF8 })
        #expect(try store.pending().map(\.actionID) == [original.actionID])
    }

    @Test func aReceiptOrAnotherLaunchClearsThePermission() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let store = try h.store(); try store.append(original)
        let none = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let client = try h.client(none, store: store); let op = try client.begin(binding: h.binding)
        _ = try await client.queryOriginal(actionID: original.actionID, operation: op)
        #expect(client.canResend(actionID: original.actionID))
        // A new launch knows nothing: it has to ask the server first.
        let reopened = try h.client(none, store: store); let next = try reopened.begin(binding: h.binding)
        #expect(!reopened.canResend(actionID: original.actionID))
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await reopened.resend(actionID: original.actionID, operation: next) }
        #expect(await none.calls.filter { $0.operation == "submitFeedback" }.isEmpty)
    }

    @Test func resendNeverSendsAnythingButTheStoredBytes() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let store = try h.store(); try store.append(original)
        let wire = Interceptor { _, _, operation in operation == "queryFeedbackAction" ? Reply(text: nullResponse) : Reply(text: "{}", status: 409) }
        let client = try h.client(wire, store: store); let op = try client.begin(binding: h.binding)
        _ = try await client.queryOriginal(actionID: original.actionID, operation: op)
        // The same ID with other bytes cannot go out as a new line, nor replace the stored one.
        let other = try FeedbackPending(problem: "Other words", expectation: "", context: nil, actionID: original.actionID)
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(other, operation: op) }
        // A refusal (409) is not a receipt and removes nothing.
        await #expect(throws: (any Error).self) { try await client.resend(actionID: original.actionID, operation: op) }
        let submits = await wire.calls.filter { $0.operation == "submitFeedback" }
        #expect(submits.count == 1 && submits[0].bytes == original.originalUTF8)
        #expect(try store.pending().map(\.actionID) == [original.actionID])
        // Tampered local bytes: nothing is sent at all.
        _ = try await client.queryOriginal(actionID: original.actionID, operation: op)
        let file = try #require(try FileManager.default.contentsOfDirectory(atPath: h.root.path).first { $0.hasSuffix(".feedback") })
        try Data(repeating: 7, count: 64).write(to: h.root.appendingPathComponent(file))
        await #expect(throws: (any Error).self) { try await client.resend(actionID: original.actionID, operation: op) }
        #expect(await wire.calls.filter { $0.operation == "submitFeedback" }.count == 1)
    }

    @Test func presentationResendsASelectedLineOnlyAfterNoSuchLine() async throws {
        let h = try Harness(); defer { h.clean() }
        let original = try pending(); let store = try h.store(); try store.append(original)
        let wire = Interceptor { _, _, operation in
            operation == "queryFeedbackAction" ? Reply(text: nullResponse) : Reply(text: try receiptJSON(original))
        }
        let model = FeedbackPresentation(client: try h.client(wire, store: store)); model.replace(binding: h.binding)
        await model.perform(try #require(model.prepareReload()))
        model.selectPending(actionID: original.actionID)
        #expect(model.prepareResend() == nil, "not asked yet")
        await model.perform(try #require(model.prepareQuery()))
        #expect(model.state == .unknown && model.receipt == nil)
        await model.perform(try #require(model.prepareResend()))
        #expect(model.state == .submitted && model.receipt != nil)
        #expect(try store.pending().isEmpty)
        #expect(await wire.calls.map(\.operation) == ["queryFeedbackAction", "submitFeedback"])
    }
}
