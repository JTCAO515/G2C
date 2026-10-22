import Foundation
import Testing
import CJAPI
import CJSession
@testable import CJManualPreviewClient

@Suite @MainActor struct LifetimeTests {
    @Test func queuedOldWorkCannotBecomeFreshAfterEditABA() async throws {
        let h = try Harness(); try await h.load(); let wire = Wire(try response(preview(h.original)))
        let editor = try h.editor(wire); let old = try editor.preparePreview()
        try editor.selectTitle(true); try editor.setTitle("temporary"); try editor.setTitle(h.original.document.title)
        await editor.perform(old)
        #expect(await wire.calls.isEmpty); #expect(editor.display()?.status == .editing)
    }
    @Test func credentialCallbackEditCannotDispatchOrEraseNewDraft() async throws {
        let h = try Harness(); try await h.load(); let wire = Wire(try response(preview(h.original)))
        var editor: PreviewEditor!
        editor = try h.editor(wire, credentials: { _ in
            try editor.selectTitle(true); try editor.setTitle("new during credentials"); return "synthetic"
        })
        let work = try editor.preparePreview(); await editor.perform(work)
        #expect(await wire.calls.isEmpty)
        #expect(editor.display()?.title == "new during credentials")
        #expect(editor.display()?.status == .editing)
    }
    @Test(arguments: [false, true]) func awaitAndBodyCollectionRetirementRejectOldResult(_ body: Bool) async throws {
        let h = try Harness(); try await h.load(); let gate = Gate()
        let wire = Wire(try response(preview(h.original)), gate: body ? nil : gate, bodyGate: body ? gate : nil)
        let editor = try h.editor(wire); let work = try editor.preparePreview()
        let task = Task { await editor.perform(work) }
        await gate.wait()
        try editor.selectTitle(true); try editor.setTitle("newer draft")
        await gate.release(); await task.value
        #expect(editor.display()?.title == "newer draft")
        #expect(editor.display()?.preview == nil); #expect(editor.display()?.status == .editing)
    }
    @Test func oldErrorCannotClearNewWork() async throws {
        let h = try Harness(); try await h.load(); let gate = Gate()
        let wire = Wire(Data("bad".utf8), gate: gate)
        let editor = try h.editor(wire); let old = try editor.preparePreview()
        let task = Task { await editor.perform(old) }; await gate.wait()
        try editor.selectTitle(true); try editor.setTitle("new draft")
        let new = try editor.preparePreview()
        await gate.release(); await task.value
        #expect(editor.display()?.status == .loading); #expect(editor.display()?.title == "new draft")
        #expect(old.id != new.id)
    }
    @Test func finalHostCallbackRetiresSourceBeforeDisplay() async throws {
        let h = try Harness(); try await h.load(); let wire = Wire(try response(preview(h.original)))
        let editor = try h.editor(wire); let work = try editor.preparePreview(); await editor.perform(work)
        #expect(editor.display()?.status == .local)
        h.callback = { h.trip.invalidateDetailSnapshots() }
        #expect(editor.display() == nil)
    }
    @Test(arguments: [1, 2, 3, 4, 5]) func finalHostCallbackEditsABABeforeSettlement(_ callbackIndex: Int) async throws {
        let h = try Harness(); try await h.load(); let gate = Gate()
        let wire = Wire(try response(preview(h.original)), gate: gate)
        let editor = try h.editor(wire); let work = try editor.preparePreview()
        let task = Task { await editor.perform(work) }; await gate.wait()
        var observed = 0; var fired = false
        h.callback = {
            observed += 1
            if observed == callbackIndex {
                h.callback = nil; fired = true
                try? editor.selectTitle(true); try? editor.setTitle("new"); try? editor.setTitle(h.original.document.title)
            }
        }
        await gate.release(); await task.value
        #expect(fired)
        #expect(editor.display()?.status == .editing); #expect(editor.display()?.preview == nil)
    }
    @Test func originalSessionRetirementAndNewSelectionHidePrivateState() async throws {
        let h = try Harness(); try await h.load(); let gate = Gate()
        let wire = Wire(try response(preview(h.original)), gate: gate)
        let editor = try h.editor(wire); let work = try editor.preparePreview()
        let task = Task { await editor.perform(work) }; await gate.wait()
        _ = try h.session.beginTrustedSDKSave()
        await gate.release(); await task.value
        #expect(editor.display() == nil)
    }
    @Test func cancelOriginalTaskSettlesOwnWorkAndPreservesInput() async throws {
        let h = try Harness(); try await h.load(); let gate = Gate()
        let wire = Wire(try response(preview(h.original)), gate: gate)
        let editor = try h.editor(wire); let work = try editor.preparePreview()
        let task = Task { await editor.perform(work) }; await gate.wait(); task.cancel()
        await gate.release(); await task.value
        #expect(editor.display()?.status == .unknown)
        #expect(editor.display()?.title == h.original.document.title)
        #expect(editor.display()?.preview == nil)
    }
    @Test func explicitCancellationAndReentryRemainOneUse() async throws {
        let h = try Harness(); try await h.load(); let gate = Gate()
        let wire = Wire(try response(preview(h.original)), gate: gate)
        let editor = try h.editor(wire); let work = try editor.preparePreview()
        let task = Task { await editor.perform(work) }; await gate.wait()
        await editor.perform(work)
        editor.cancelPreview(); await gate.release(); await task.value
        #expect(editor.display()?.status == .unknown); #expect(await wire.calls.count == 1)
    }
}
