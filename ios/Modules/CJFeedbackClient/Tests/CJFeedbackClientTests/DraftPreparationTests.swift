import Testing
import Foundation
import CJAPI
@testable import CJFeedbackClient

@MainActor struct DraftPreparationTests {
    @Test(arguments: ["problem", "expectation", "association", "aba"])
    func acceptedCallbackChangesRetirePreparation(field: String) async throws {
        let h = try Harness(); defer { h.clean() }
        let wire = Interceptor { _, _, _ in Reply(text: nullResponse) }
        let model = FeedbackPresentation(client: try h.client(wire))
        model.replace(binding: h.binding, context: try FeedbackContext(messageID: "消息e\u{301}", runID: "运行"))
        model.edit(problem: "before", expectation: "before expectation")
        h.onBinding = {
            h.onBinding = nil
            switch field {
            case "problem": model.edit(problem: "after", expectation: model.expectation)
            case "expectation": model.edit(problem: model.problem, expectation: "after expectation")
            case "association": model.associateContext(true)
            default:
                model.edit(problem: "temporary", expectation: "temporary expectation")
                model.edit(problem: "before", expectation: "before expectation")
            }
        }
        #expect(model.prepareSubmit() == nil)
        #expect(model.original == nil && model.receipt == nil && model.state == .editing)
        #expect(model.problem == (field == "problem" ? "after" : "before"))
        #expect(model.expectation == (field == "expectation" ? "after expectation" : "before expectation"))
        #expect(model.includeContext == (field == "association"))
        #expect(await wire.calls.isEmpty)
        #expect(try h.store().pending().isEmpty)
        // A later explicit click captures exactly the accepted editor, with no automatic resend.
        #expect(model.prepareSubmit() != nil)
        let action = try #require(model.original).action()
        #expect(same(action.problem, model.problem) && same(action.expectation, model.expectation))
        #expect(action.references.count == (field == "association" ? 2 : 0))
        #expect(await wire.calls.isEmpty)
    }

    private func successfulWire() -> Interceptor {
        Interceptor { _, bytes, _ in
            let action = try JSONDecoder().decode(Components.Schemas.FeedbackAction.self, from: bytes)
            let original = try FeedbackPending(problem: action.problem, expectation: action.expectation, context: nil, actionID: action.action_id)
            return Reply(text: try receiptJSON(original, hash: digest(bytes)))
        }
    }

    @Test func nextExplicitSubmitConfirmsOnlyAcceptedDraft() async throws {
        let h = try Harness(); defer { h.clean() }; let wire = successfulWire()
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding)
        model.edit(problem: "first", expectation: "first expectation")
        h.onBinding = { h.onBinding = nil; model.edit(problem: "accepted edit", expectation: "accepted expectation") }
        #expect(model.prepareSubmit() == nil)
        #expect(await wire.calls.isEmpty)
        let work = try #require(model.prepareSubmit())
        await model.perform(work)
        #expect(model.state == .submitted)
        let calls = await wire.calls
        #expect(calls.count == 1)
        let call = try #require(calls.first)
        let sent = try JSONDecoder().decode(Components.Schemas.FeedbackAction.self, from: call.bytes)
        #expect(same(sent.problem, model.problem) && same(sent.expectation, model.expectation))
        #expect(model.problem == "accepted edit")
        #expect(model.receipt?.input_sha256 == digest(call.bytes))
    }

    @Test func lockedOriginalRejectsCallbackEditWithoutInvalidatingQuery() async throws {
        let h = try Harness(); defer { h.clean() }; let original = try pending(); let store = try h.store()
        try store.append(original)
        let body = try receiptJSON(original)
        let wire = Interceptor { _, _, _ in Reply(text: body) }
        let model = FeedbackPresentation(client: try h.client(wire, store: store)); model.replace(binding: h.binding)
        await model.perform(try #require(model.prepareReload())); model.selectPending(actionID: original.actionID)
        let beforeProblem = model.problem; let beforeExpectation = model.expectation
        var editAttempted = false
        h.onBinding = {
            h.onBinding = nil; editAttempted = true
            model.edit(problem: "not accepted", expectation: "not accepted")
            model.associateContext(true)
        }
        await model.perform(try #require(model.prepareQuery()))
        #expect(editAttempted && model.state == .submitted)
        #expect(same(model.problem, beforeProblem) && same(model.expectation, beforeExpectation))
        #expect(model.original?.originalUTF8 == original.originalUTF8 && !model.includeContext)
        #expect(await wire.calls.map(\.operation) == ["queryFeedbackAction"])
    }

    @Test func frozenQueuedSubmitRejectsEditsAndPreservesExactDisplay() async throws {
        let h = try Harness(); defer { h.clean() }; let wire = successfulWire()
        let model = FeedbackPresentation(client: try h.client(wire)); model.replace(binding: h.binding)
        model.edit(problem: "original", expectation: "original expectation")
        let work = try #require(model.prepareSubmit()); let original = try #require(model.original)
        h.onBinding = { h.onBinding = nil; model.edit(problem: "rejected", expectation: "rejected") }
        await model.perform(work)
        #expect(model.state == .submitted && model.problem == "original" && model.expectation == "original expectation")
        #expect(model.original?.originalUTF8 == original.originalUTF8)
        #expect(await wire.calls.first?.bytes == original.originalUTF8)
    }
}
