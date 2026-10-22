import Testing
import Foundation
import CryptoKit
import CJAPI
@testable import CJFeedbackClient

@MainActor struct LifecycleTests {
    @Test(arguments: ["account", "selection", "environment", "generation"]) func credentialCallbackCannotCrossBinding(kind: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending()
        let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let client = try h.client(wire, credentials: { binding in
            h.current = FeedbackBinding(environment: kind == "environment" ? UUID() : binding.environment,
                                        account: kind == "account" ? UUID() : binding.account,
                                        generation: kind == "generation" ? UUID() : binding.generation,
                                        selection: kind == "selection" ? UUID() : binding.selection)
            return "synthetic"
        })
        let op = try client.begin(binding: h.binding)
        await #expect(throws: FeedbackFailure.staleBinding) { try await client.submit(original, operation: op) }
        #expect(await wire.calls.isEmpty)
        #expect(try h.store().pending().first?.originalUTF8 == original.originalUTF8)
    }
    @Test func responseAfterAccountSwitchCannotPublish() async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(); let gate = Gate()
        let body = try receiptJSON(original)
        let wire = Interceptor { _, _, _ in await gate.park(); return Reply(text: body) }
        let client = try h.client(wire); let op = try client.begin(binding: h.binding)
        let task = Task { try await client.submit(original, operation: op) }
        await gate.waitForEntry(); h.current = nil; await gate.release()
        await #expect(throws: FeedbackFailure.staleBinding) { try await task.value }
        #expect(try h.store().pending().count == 1)
    }
    @Test func sameBindingInvalidationDuringCredentialCallback() async throws {
        let h = try Harness(); defer { h.clean() }; let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        var client: FeedbackClient!
        client = try h.client(wire, credentials: { _ in client.invalidate(); return "synthetic" })
        let op = try client.begin(binding: h.binding)
        await #expect(throws: FeedbackFailure.staleBinding) { try await client.submit(pending(), operation: op) }
        #expect(await wire.calls.isEmpty)
    }
    @Test func bindingCallbackReentryCannotReturnOldOperation() throws {
        let h = try Harness(); defer { h.clean() }; let client = try h.client(Interceptor { _, _, _ in Reply(text: nullResponse) })
        h.onBinding = { h.onBinding = nil; client.invalidate() }
        #expect(throws: FeedbackFailure.staleBinding) { try client.begin(binding: h.binding) }
    }
    @Test func sameBindingKeyCallbackReentryBlocksAppend() async throws {
        let h = try Harness(); defer { h.clean() }; let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        var client: FeedbackClient!
        let store = try h.store { client.invalidate(); return h.key }
        client = try h.client(wire, store: store)
        let op = try client.begin(binding: h.binding)
        await #expect(throws: FeedbackFailure.staleBinding) { try await client.submit(pending(), operation: op) }
        #expect(await wire.calls.isEmpty)
        #expect(try FileManager.default.contentsOfDirectory(atPath: h.root.path).isEmpty)
    }
    @Test(arguments: ["directory", "ciphertext"]) func finalBindingCallbackCannotReplaceDurability(kind: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(); let store = try h.store(); try store.append(original)
        let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        var arm = false; var swap = false
        let guarded = try h.store {
            if arm { arm = false; swap = true }
            return h.key
        }
        let client = try h.client(wire, store: guarded, credentials: { _ in arm = true; return "synthetic" })
        h.onBinding = {
            guard swap else { return }; swap = false
            if kind == "directory" {
                try! FileManager.default.moveItem(at: h.root, to: h.root.appendingPathExtension("moved"))
                try! FileManager.default.createDirectory(at: h.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            } else {
                let file = h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".feedback")
                var bytes = try! Data(contentsOf: file); bytes[0] ^= 1; try! bytes.write(to: file)
            }
        }
        let op = try client.begin(binding: h.binding)
        await #expect(throws: (any Error).self) { try await client.queryOriginal(actionID: original.actionID, operation: op) }
        #expect(await wire.calls.isEmpty)
    }
    @Test(arguments: ["directory", "ciphertext"]) func lastKeyCallbackCannotReplaceOriginal(kind: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(); try h.store().append(original)
        var arm = false
        let store = try h.store {
            if arm {
                arm = false
                if kind == "directory" {
                    try FileManager.default.moveItem(at: h.root, to: h.root.appendingPathExtension("moved"))
                    try FileManager.default.createDirectory(at: h.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
                } else {
                    let file = h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".feedback")
                    var bytes = try Data(contentsOf: file); bytes[0] ^= 1; try bytes.write(to: file)
                }
            }
            return h.key
        }
        let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let client = try h.client(wire, store: store, credentials: { _ in arm = true; return "synthetic" })
        await #expect(throws: (any Error).self) { try await client.queryOriginal(actionID: original.actionID, operation: client.begin(binding: h.binding)) }
        #expect(await wire.calls.isEmpty)
    }
    @Test func cancelledExchangeKeepsOriginal() async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate(); let original = try pending()
        let wire = Interceptor { _, _, _ in await gate.park(); return Reply(text: nullResponse) }
        let client = try h.client(wire); let op = try client.begin(binding: h.binding)
        let task = Task { try await client.submit(original, operation: op) }
        await gate.waitForEntry(); task.cancel(); await gate.release()
        await #expect(throws: CancellationError.self) { try await task.value }
        #expect(try h.store().pending().count == 1)
        await #expect(throws: FeedbackFailure.pendingRequiresQuery) { try await client.submit(original, operation: op) }
    }
    @Test func clientOwnershipAndInventoryFence() throws {
        let h = try Harness(); defer { h.clean() }; let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let client = try h.client(wire); let other = try h.client(wire); let op = try client.begin(binding: h.binding)
        #expect(throws: FeedbackFailure.staleBinding) { try other.pending(operation: op) }
        let original = try pending(); let store = try h.store(); try store.append(original)
        var armed = true
        h.onBinding = {
            if armed { armed = false; try! store.append(pending(actionID: "second")) }
        }
        let records = try client.pending(operation: op)
        #expect(records.count == 2)
        let proof = try store.requireOriginal(original)
        try FileManager.default.removeItem(at: h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".feedback"))
        #expect(throws: (any Error).self) { try store.validateDurability(proof) }
    }
}

@MainActor struct FinalResponseTests {
    @Test(arguments: ["directory", "ciphertext"]) func replacementAfterResponseWithholdsConfirmation(kind: String) async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(); let response = try receiptJSON(original)
        var arm = false; var swap = false
        let store = try h.store { if arm { arm = false; swap = true }; return h.key }
        h.onBinding = {
            guard swap else { return }; swap = false
            if kind == "directory" {
                try! FileManager.default.moveItem(at: h.root, to: h.root.appendingPathExtension("moved"))
                try! FileManager.default.createDirectory(at: h.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
            } else {
                let file = h.root.appendingPathComponent(digest(Data(original.actionID.utf8)) + ".feedback")
                var bytes = try! Data(contentsOf: file); bytes[0] ^= 1; try! bytes.write(to: file)
            }
        }
        let wire = Interceptor { _, _, _ in await MainActor.run { arm = true }; return Reply(text: response) }
        let client = try h.client(wire, store: store)
        await #expect(throws: FeedbackFailure.exchangeUnknown) { try await client.submit(original, operation: client.begin(binding: h.binding)) }
        #expect(await wire.calls.count == 1)
    }
}
