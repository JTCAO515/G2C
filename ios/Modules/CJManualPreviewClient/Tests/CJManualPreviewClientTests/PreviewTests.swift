import Foundation
import Testing
import CJAPI
import CJSession
import CJMessageHTTP
@testable import CJManualPreviewClient

@Suite @MainActor struct PreviewTests {
    @Test func noOpUsesFormalOriginalAndExactFrozenRequest() async throws {
        let h = try Harness(); try await h.load()
        let wire = Wire(try response(preview(h.original)))
        let editor = try h.editor(wire); let work = try editor.preparePreview()
        await editor.perform(work)
        #expect(editor.display()?.status == .local)
        #expect(editor.display()?.preview?.diff.isEmpty == true)
        #expect(work.request.expected_version == 7)
        #expect(work.request.original_content_utf8_base64 == h.original.content_utf8_base64)
        #expect(await wire.calls == [work.bytes])
        let json = try #require(try JSONSerialization.jsonObject(with: work.bytes) as? [String: Any])
        #expect(json["title"] is NSNull); #expect(json["order"] is NSNull)
        await editor.perform(work); #expect(await wire.calls.count == 1)
        #expect(String(reflecting: work) == "<readonly manual preview work>")
    }
    @Test func titleTextOrderAndNFDUseServerDiff() async throws {
        let h = try Harness(); try await h.load()
        var after = h.original.document
        after.title = " New e\u{301} "
        after.items[0].text = "Changed e\u{301}"; after.items[0].verification = .pending; after.items[0].evidence = []
        after.items.swapAt(0, 1)
        let diff = try [change(["title"], h.original.document.title, after.title),
                        change(["items", "order"], ["a", "b", "c"], ["b", "a", "c"]),
                        change(["items", "id", "a"], h.original.document.items[0], after.items[1])]
        let p = try preview(h.original, after: after, selected: ["a", "b"], titleSelected: true, diff: diff)
        let wire = Wire(try response(p)); let editor = try h.editor(wire)
        try editor.selectTitle(true); try editor.setTitle(after.title)
        try editor.selectItem("a", selected: true); try editor.selectItem("b", selected: true)
        try editor.setText(after.items[1].text, for: "a"); try editor.setOrder(["b", "a", "c"])
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.status == .local)
        #expect(try encoded(editor.display()?.preview) == encoded(p))
        #expect(work.bytes.range(of: Data("e\u{301}".utf8)) != nil)
        #expect(work.bytes.range(of: Data("é".utf8)) == nil)
    }
    @Test(arguments: ["title", "item", "order"]) func individualEdits(_ kind: String) async throws {
        let h = try Harness(); try await h.load()
        var after = h.original.document
        let selected = kind == "title" ? [] : (kind == "item" ? ["a"] : ["a", "b"])
        let diff: [Components.Schemas.ManualPreviewChange]
        switch kind {
        case "title":
            after.title = "Title only"
            diff = [try change(["title"], h.original.document.title, after.title)]
        case "item":
            after.items[0].text = "Item only"; after.items[0].verification = .pending; after.items[0].evidence = []
            diff = [try change(["items", "id", "a"], h.original.document.items[0], after.items[0])]
        default:
            after.items.swapAt(0, 1)
            diff = [try change(["items", "order"], ["a", "b", "c"], ["b", "a", "c"])]
        }
        let wire = Wire(try response(preview(h.original, after: after, selected: selected, titleSelected: kind == "title", diff: diff)))
        let editor = try h.editor(wire)
        for id in selected { try editor.selectItem(id, selected: true) }
        if kind == "title" { try editor.selectTitle(true); try editor.setTitle(after.title) }
        if kind == "item" { try editor.setText(after.items[0].text, for: "a") }
        if kind == "order" { try editor.setOrder(["b", "a", "c"]) }
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.status == .local)
        #expect(editor.display()?.preview?.diff.count == 1)
    }
    @Test func existingLiveTransportGateIsVisibleAndRetainsDraft() async throws {
        let h = try Harness(); try await h.load()
        let transport = try NoRedirectTransport(requestTimeout: 1, resourceTimeout: 1)
        let editor = try PreviewEditor(trip: h.trip, source: h.snapshot, endpoint: h.endpoint,
            session: h.session, operation: h.operation, credentials: { _ in "synthetic" }, liveTransport: transport)
        try editor.selectTitle(true); try editor.setTitle("Retain at production gate")
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.status == .unavailable)
        #expect(editor.display()?.preview == nil)
        #expect(editor.display()?.title == "Retain at production gate")
    }
    @Test func explicitRequestLimitRetainsOversizedInput() async throws {
        let h = try Harness(); try await h.load()
        let editor = try h.editor(Wire(try response(preview(h.original))))
        try editor.selectTitle(true); let text = String(repeating: "a", count: 100_001); try editor.setTitle(text)
        #expect(throws: PreviewFailure.invalidInput) { try editor.preparePreview() }
        #expect(editor.display()?.title == text)
    }
    @Test(arguments: [409, 503]) func conflictsAndUnknownRetainDraftAndExactRetry(_ code: Int) async throws {
        let h = try Harness(); try await h.load()
        let error = try encoded(Components.Schemas.ErrorResponse(request_id: trace, error: .init(code: "UNAVAILABLE", category: "base", message_en: "Unavailable", message_zh: "不可用", outcome: .unknown, recovery: .do_not_retry)))
        let wire = Wire(error, code: code); let editor = try h.editor(wire)
        try editor.selectTitle(true); try editor.setTitle("User original draft")
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.title == "User original draft")
        #expect(editor.display()?.preview == nil)
        let retry = try editor.preparePreview(); #expect(retry.bytes == work.bytes)
        await editor.perform(retry); #expect(await wire.calls.count == 2)
        #expect(editor.display()?.status == (code == 409 ? .conflict : .unknown))
    }
    @Test(arguments: ["can-save", "wrong-version", "wrong-original", "scope", "unselected", "missing-diff", "diff-value", "projection"])
    func rejectsInconsistentSuccess(_ fault: String) async throws {
        let h = try Harness(); try await h.load()
        var p = try preview(h.original)
        switch fault {
        case "can-save": p.can_save = true
        case "wrong-version": p.original.version += 1
        case "wrong-original": p.original.content_utf8_base64 = Data("{}".utf8).base64EncodedString()
        case "scope": p.selected_ids = ["a"]
        case "unselected": p.document.items[0].text = "Injected"
        case "missing-diff": p.document.title = "Injected"
        case "diff-value": p.diff = [try change(["title"], "bad", "bad2")]
        default: p.content_utf8_base64 = Data("{}".utf8).base64EncodedString()
        }
        let editor = try h.editor(Wire(try response(p))); let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.preview == nil)
        #expect(editor.display()?.status == .invalidResponse)
        #expect(editor.display()?.title == h.original.document.title)
    }
    @Test(arguments: ["missing", "null", "enum", "duplicate", "trace", "cache", "overlimit"])
    func rejectsMalformedBodiesAndHeaders(_ fault: String) async throws {
        let h = try Harness(); try await h.load()
        var raw = String(decoding: try response(preview(h.original)), as: UTF8.self)
        switch fault {
        case "missing": raw = raw.replacingOccurrences(of: "\"can_save\":false,", with: "")
        case "null": raw = raw.replacingOccurrences(of: "\"can_save\":false", with: "\"can_save\":null")
        case "enum": raw = raw.replacingOccurrences(of: "UNKNOWN", with: "UNLOCKED")
        case "duplicate": raw = raw.replacingOccurrences(of: "\"can_save\":false", with: "\"can_save\":false,\"can_save\":false")
        case "overlimit": raw = String(repeating: " ", count: 100_001) + raw
        default: break
        }
        let wire = Wire(Data(raw.utf8), trace: fault == "trace" ? UUID().uuidString : trace, cache: fault == "cache" ? nil : "no-store")
        let editor = try h.editor(wire); let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.preview == nil); #expect(editor.display()?.status != .local)
    }
    @Test func selectionAndScopeRejectInvalidEdits() async throws {
        let h = try Harness(); try await h.load(); let editor = try h.editor(Wire(try response(preview(h.original))))
        #expect(throws: PreviewFailure.invalidInput) { try editor.setTitle("x") }
        #expect(throws: PreviewFailure.invalidInput) { try editor.setText("x", for: "a") }
        #expect(throws: PreviewFailure.invalidInput) { try editor.selectItem("unknown", selected: true) }
        try editor.selectItem("a", selected: true)
        #expect(throws: PreviewFailure.invalidInput) { try editor.setOrder(["b", "a", "c"]) }
        #expect(throws: PreviewFailure.invalidInput) { try editor.setOrder(["a", "a", "c"]) }
    }
}
