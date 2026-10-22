import Testing
import Foundation
import CryptoKit
import CJAPI
@testable import CJNeedsClient

@MainActor @Suite struct BoundaryTests {
    @Test func queuedSelectionAndDuplicateWorkCannotDispatch() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); let t = successfulTransport(a)
        let client = try h.client(t); let model = NeedsPresentation(client: client); model.replace(binding: h.binding)
        let old = try #require(model.prepareDetail(id: "old"))
        let next = try #require(model.prepareDetail(id: a.needsID))
        await model.perform(old); #expect(await t.calls.isEmpty); #expect(model.state == .loading && model.selectedNeedsID == a.needsID)
        await model.perform(next); await model.perform(next)
        #expect(await t.calls.count == 1 && model.state == .loaded)
        let foreign = NeedsPresentation(client: client); foreign.replace(binding: h.binding)
        await foreign.perform(next); #expect(await t.calls.count == 1)
    }
    @Test func queuedOriginalActionCannotBecomeAdjacentNewAction() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original("A"); let b = try original("B")
        let store = try h.store(); try store.append(a); try store.append(b)
        let t = successfulTransport(b); let model = NeedsPresentation(client: try h.client(t, store: store)); model.replace(binding: h.binding)
        let old = try #require(model.prepareQuery(actionID: a.actionID)); let new = try #require(model.prepareQuery(actionID: b.actionID))
        await model.perform(old); #expect(await t.calls.isEmpty && model.selectedActionID == "B")
        await model.perform(new); #expect(model.receipt?.action_id == "B")
        #expect(await t.calls.first?.path?.contains("action_id=B") == true)
    }
    @Test(arguments: [false, true]) func credentialReentryKeepsNewSelection(throwsAfter: Bool) async throws {
        let h = try Harness(); defer { h.clean() }; let t = successfulTransport(try original())
        var model: NeedsPresentation!
        let client = try h.client(t, credentials: { _ in
            _ = model.prepareDetail(id: "new-selection")
            if throwsAfter { throw NeedsFailure.unconfigured }
            return "synthetic"
        })
        model = NeedsPresentation(client: client); model.replace(binding: h.binding)
        let work = try #require(model.prepareDetail(id: "old")); await model.perform(work)
        #expect(model.selectedNeedsID == "new-selection" && model.state == .loading)
        #expect(await t.calls.isEmpty)
    }
    @Test func bindingCallbackReentryCannotAdoptNewWork() async throws {
        let h = try Harness(); defer { h.clean() }; let t = successfulTransport(try original())
        var model: NeedsPresentation!; var fired = false
        let client = try h.client(t, bindingCallback: {
            if !fired { fired = true; _ = model.prepareDetail(id: "B") }
            return h.binding
        })
        model = .init(client: client); model.replace(binding: h.binding)
        let old = try #require(model.prepareDetail(id: "A")); await model.perform(old)
        #expect(model.selectedNeedsID == "B" && model.state == .loading && model.snapshot == nil)
        #expect(await t.calls.isEmpty)
    }
    @Test(arguments: [false, true]) func keyCallbackReentryCannotPersistOldAction(throwsAfter: Bool) async throws {
        let h = try Harness(); defer { h.clean() }; let t = successfulTransport(try original())
        var model: NeedsPresentation!; var fired = false
        let store = try h.store(key: {
            if !fired {
                fired = true; model.beginNew(id: "B")
                if throwsAfter { throw NeedsFailure.keyUnavailable }
            }
            return h.key
        })
        model = NeedsPresentation(client: try h.client(t, store: store)); model.replace(binding: h.binding)
        model.beginNew(id: "A"); model.draft?.sourceText = "A"; model.draft?.set(.pace, .init(state: .known, value: "slow"))
        let old = try #require(model.prepareSave(actionID: "A-action")); await model.perform(old)
        #expect(model.selectedNeedsID == "B" && model.state == .idle)
        #expect(try store.pending().isEmpty); #expect(await t.calls.isEmpty)
    }
    @Test(arguments: [false, true]) func lastBindingCallbackReplacesDirectoryOrCiphertextBeforeOutflow(fileOnly: Bool) async throws {
        let h = try Harness(); defer { h.clean() }
        let displaced = h.root.appendingPathExtension("displaced"); defer { try? FileManager.default.removeItem(at: displaced) }
        var keys = 0; var moved = false
        let store = try h.store(key: { keys += 1; return h.key })
        let t = successfulTransport(try original())
        let client = try h.client(t, store: store, bindingCallback: {
            if keys == 2 && !moved {
                moved = true
                if fileOnly {
                    let file = try! FileManager.default.contentsOfDirectory(at: h.root, includingPropertiesForKeys: nil)[0]
                    try! FileManager.default.moveItem(at: file, to: displaced)
                } else {
                    try! FileManager.default.moveItem(at: h.root, to: displaced)
                    try! FileManager.default.createDirectory(at: h.root, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
                }
            }
            return h.binding
        })
        await #expect(throws: (any Error).self) { try await client.perform(client.prepareManualAction(try original(), binding: h.binding)) }
        #expect(moved); #expect(await t.calls.isEmpty)
        #expect(FileManager.default.fileExists(atPath: displaced.path))
    }
    @Test func ciphertextChangedByLastCallbackCannotSettle() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); var keys = 0; var mutate = false; var changed = false
        let store = try h.store(key: { keys += 1; return h.key }); try store.append(a)
        let t = Interceptor { _, _, op in
            if op == "queryNeedsAction" { return Reply(try response("receipt", receipt(a))) }
            return Reply(try response("revision", revision(a)))
        }
        // The final settlement key read follows: append1, pending2, query transport3..5,
        // revision transport6..8, settlement9. Last binding callback then corrupts original.
        let client = try h.client(t, store: store, bindingCallback: {
            if mutate && keys == 9 && !changed {
                changed = true
                let file = try! FileManager.default.contentsOfDirectory(at: h.root, includingPropertiesForKeys: nil)[0]
                var bytes = try! Data(contentsOf: file); bytes[0] ^= 1; try! bytes.write(to: file)
            }
            return h.binding
        })
        mutate = true
        await #expect(throws: (any Error).self) { try await client.perform(client.prepareQuery(actionID: a.actionID, binding: h.binding)) }
        #expect(changed); #expect(await t.calls.count == 2)
    }
    @Test func accountSwitchWhileRequestSuspendedRejectsLateResult() async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate(); let a = try original()
        let t = Interceptor { _, _, _ in await gate.park(); return Reply(try response("needs", snapshot(a))) }
        let model = NeedsPresentation(client: try h.client(t)); model.replace(binding: h.binding)
        let work = try #require(model.prepareDetail(id: a.needsID)); let task = Task { await model.perform(work) }
        await gate.waitForEntry()
        let b = NeedsBinding(environment: h.binding.environment, account: UUID(), generation: UUID(), selection: UUID()); h.current = b; model.replace(binding: b)
        model.beginNew(id: "B"); await gate.release(); await task.value
        #expect(model.selectedNeedsID == "B" && model.state == .idle && model.snapshot == nil)
    }
    @Test(arguments: [false, true]) func cancellationSettlesLoadingWithoutResend(write: Bool) async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate(); let a = try original()
        let t = Interceptor { _, _, operation in
            await gate.park()
            return Reply(try operation == "actOnNeeds" ? response("receipt", receipt(a)) : response("needs", snapshot(a)))
        }
        let model = NeedsPresentation(client: try h.client(t)); model.replace(binding: h.binding)
        let work: NeedsPresentationWork
        if write {
            model.beginNew(id: a.needsID); model.draft?.sourceText = a.command.source.text; model.draft?.set(.partySize, .init(state: .known, value: "3"))
            work = try #require(model.prepareSave(actionID: a.actionID))
        } else { work = try #require(model.prepareDetail(id: a.needsID)) }
        let task = Task { await model.perform(work) }; await gate.waitForEntry(); task.cancel(); await gate.release(); await task.value
        #expect(model.state == (write ? .unknown : .cancelled)); #expect(await t.calls.count == 1)
    }
    @Test func conflictPreservesDraftAndOriginalVersionAfterLatestRead() async throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(version: 4)
        let t = Interceptor { _, _, op in
            if op == "actOnNeeds" {
                let error = NeedsSchema.ErrorResponse(request_id: trace, error: .init(code: "conflict", category: "conflict", message_en: "conflict", message_zh: "冲突", outcome: .failed, recovery: .do_not_retry))
                return Reply(String(decoding: try encoded(error), as: UTF8.self), status: 409)
            }
            return Reply(try response("needs", snapshot(a)))
        }
        let model = NeedsPresentation(client: try h.client(t)); model.replace(binding: h.binding)
        model.beginNew(id: a.needsID); model.draft?.sourceText = "my correction"; model.draft?.set(.pace, .init(state: .known, value: "慢 / slow"))
        let save = try #require(model.prepareSave(actionID: "correction")); await model.perform(save)
        #expect(model.state == .conflict && model.draft?.expectedVersion == 0)
        #expect(model.draft?.observations[.pace]?.value == "慢 / slow")
        let latest = try #require(model.prepareDetail(id: a.needsID)); await model.perform(latest)
        #expect(model.snapshot?.version == 5 && model.draft?.expectedVersion == 0 && model.draft?.sourceText == "my correction")
        #expect(await t.calls.filter { $0.operation == "actOnNeeds" }.count == 1)
    }
    @Test func pendingNestedLoadFailureDoesNotOverwriteNewResult() throws {
        let h = try Harness(); defer { h.clean() }; let a = try original(); try h.store().append(a)
        var model: NeedsPresentation!; var fired = false
        let store = try h.store(key: {
            if !fired { fired = true; model.loadPending(); throw NeedsFailure.keyUnavailable }
            return h.key
        })
        model = NeedsPresentation(client: try h.client(successfulTransport(a), store: store)); model.replace(binding: h.binding)
        model.loadPending()
        #expect(model.pendingState == .loaded && model.pendingActions.count == 1)
    }
}

@MainActor @Suite struct SelectionTests {
    @Test func historicalSelectionCannotKeepAnotherRecordsEditor() async throws {
        let h = try Harness(); defer { h.clean() }
        let a = try original(); let model = NeedsPresentation(client: try h.client(successfulTransport(a)))
        model.replace(binding: h.binding); model.beginNew(id: "other-record")
        model.draft?.sourceText = "other record edits"
        let work = try #require(model.prepareRevision(id: a.needsID, version: 1))
        #expect(model.draft == nil); await model.perform(work)
        #expect(model.revision?.needs_id == a.needsID && model.draft == nil)
    }
}
