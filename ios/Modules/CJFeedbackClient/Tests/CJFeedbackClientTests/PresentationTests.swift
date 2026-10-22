import Testing
import Foundation
import CJAPI
@testable import CJFeedbackClient

@MainActor struct PresentationTests {
    @Test func queuedOldSubmitCannotUseNewContext() async throws {
        let h = try Harness(); defer { h.clean() }; let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding, context: try FeedbackContext(messageID: "old"))
        #expect(model.problem.isEmpty && model.expectation.isEmpty && !model.includeContext)
        model.edit(problem: "voluntary", expectation: "expected"); model.associateContext(true)
        let work = try #require(model.prepareSubmit())
        model.replace(binding: h.binding, context: try FeedbackContext(messageID: "new"))
        model.edit(problem: "new editor", expectation: "new expectation")
        await model.perform(work)
        #expect(await wire.calls.isEmpty); #expect(model.problem == "new editor"); #expect(model.original == nil)
    }
    @Test func queuedOldQueryCannotQueryNewSelection() async throws {
        let h = try Harness(); defer { h.clean() }; let store = try h.store()
        try store.append(pending(actionID: "first")); try store.append(pending(actionID: "second"))
        let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let model = FeedbackPresentation(client: try h.client(wire, store: store)); model.replace(binding: h.binding)
        await model.perform(try #require(model.prepareReload()))
        model.selectPending(actionID: "first"); let work = try #require(model.prepareQuery()); model.selectPending(actionID: "second")
        await model.perform(work)
        #expect(await wire.calls.isEmpty); #expect(model.original?.actionID == "second"); #expect(model.state == .unknown)
    }
    @Test func sameBindingSelectionReentryFromKeyDoesNotPublishOrClearNewState() async throws {
        let h = try Harness(); defer { h.clean() }; let base = try h.store()
        try base.append(pending(actionID: "first")); try base.append(pending(actionID: "second"))
        var model: FeedbackPresentation!; var armed = false
        let store = try h.store { if armed { armed = false; model.selectPending(actionID: "second") }; return h.key }
        let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        model = FeedbackPresentation(client: try h.client(wire, store: store)); model.replace(binding: h.binding)
        await model.perform(try #require(model.prepareReload()))
        model.selectPending(actionID: "first"); let work = try #require(model.prepareQuery()); armed = true
        await model.perform(work)
        #expect(await wire.calls.isEmpty); #expect(model.original?.actionID == "second"); #expect(model.state == .unknown)
    }
    @Test func bindingReentryDuringPrepareDoesNotFreezeOldDraft() throws {
        let h = try Harness(); defer { h.clean() }; let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding); model.edit(problem: "old", expectation: "")
        h.onBinding = {
            h.onBinding = nil; model.replace(binding: h.binding); model.edit(problem: "new", expectation: "")
        }
        #expect(model.prepareSubmit() == nil); #expect(model.problem == "new"); #expect(model.original == nil); #expect(model.state == .editing)
    }
    @Test func duplicateWorkIsOneShotAndCancellationSettlesBusy() async throws {
        let h = try Harness(); defer { h.clean() }; let gate = Gate()
        let wire = Interceptor { _, _, _ in await gate.park(); return Reply(text: nullResponse) }
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding); model.edit(problem: "private", expectation: "")
        let work = try #require(model.prepareSubmit()); let task = Task { await model.perform(work) }
        await gate.waitForEntry(); await model.perform(work); task.cancel(); await gate.release(); await task.value
        #expect(model.state == .unknown); #expect(!model.state.isBusy); #expect(model.problem == "private"); #expect(model.original != nil)
        #expect(await wire.calls.count == 1)
    }
    @Test func missingBindingBeforeQueuedWorkDoesNotHangBusy() async throws {
        let h = try Harness(); defer { h.clean() }; let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding); model.edit(problem: "private", expectation: "")
        let work = try #require(model.prepareSubmit()); h.current = nil; await model.perform(work)
        #expect(model.state == .recoveryUnavailable); #expect(!model.state.isBusy); #expect(await wire.calls.isEmpty)
    }
    @Test func conflictRetainsOriginalDraftAndRecovery() async throws {
        let h = try Harness(); defer { h.clean() }
        let error = """
        {"request_id":"\(trace)","error":{"code":"FEEDBACK_CONFLICT","category":"conflict","outcome":"failed","message_en":"Conflict","message_zh":"冲突","recovery":"reconcile_original"}}
        """
        let wire = Interceptor { _, _, operation in Reply(text: operation == "submitFeedback" ? error : nullResponse, status: operation == "submitFeedback" ? 409 : 200) }
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding); model.edit(problem: "private problem", expectation: "private expectation")
        await model.perform(try #require(model.prepareSubmit()))
        #expect(model.state == .conflict); #expect(model.problem == "private problem"); #expect(model.expectation == "private expectation")
        let bytes = try #require(model.original?.originalUTF8)
        await model.perform(try #require(model.prepareQuery()))
        #expect(model.state == .unknown); #expect(model.original?.originalUTF8 == bytes)
        #expect(model.prepareSubmit() == nil); #expect(try h.store().pending().count == 1)
    }
    @Test func confirmationComesOnlyFromReceipt() async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, bytes, _ in
            let action = try JSONDecoder().decode(Components.Schemas.FeedbackAction.self, from: bytes)
            let original = try FeedbackPending(problem: action.problem, expectation: action.expectation, context: nil, actionID: action.action_id)
            return Reply(text: try receiptJSON(original))
        }
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding); model.edit(problem: "private", expectation: "")
        await model.perform(try #require(model.prepareSubmit()))
        #expect(model.state == .submitted); #expect(model.receipt != nil); #expect(model.original != nil)
    }
}
