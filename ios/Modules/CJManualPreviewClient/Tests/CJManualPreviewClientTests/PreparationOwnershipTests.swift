import Foundation
import Testing
@testable import CJManualPreviewClient

@Suite @MainActor struct PreparationOwnershipTests {
    @Test(arguments: [1, 2]) func newerPreparationSurvivesEitherOuterSourceCallback(_ callbackIndex: Int) async throws {
        let h = try Harness(); try await h.load()
        let wire = Wire(try response(preview(h.original))); let state = try h.editor(wire)
        var newer: PreviewWork?; var calls = 0
        h.callback = {
            calls += 1
            if calls == callbackIndex {
                h.callback = nil
                newer = try? state.preparePreview()
            }
        }
        #expect(throws: PreviewFailure.retired) { try state.preparePreview() }
        let valid = try #require(newer)
        await state.perform(valid)
        #expect(await wire.calls.count == 1); #expect(state.display()?.status == .local)
        await state.perform(valid)
        #expect(await wire.calls.count == 1)
    }
    @Test func repeatedPreparationNeedsNoOlderCallerToUnlock() async throws {
        let h = try Harness(); try await h.load()
        let wire = Wire(try response(preview(h.original))); let state = try h.editor(wire)
        let old = try state.preparePreview()
        let newer = try state.preparePreview()
        await state.perform(newer)
        #expect(state.display()?.status == .local); #expect(await wire.calls.count == 1)
        await state.perform(old)
        #expect(state.display()?.status == .local); #expect(await wire.calls.count == 1)
    }
    @Test func callbackCancellationOrEditStillRetiresPreparation() async throws {
        for cancel in [false, true] {
            let h = try Harness(); try await h.load()
            let wire = Wire(try response(preview(h.original))); let state = try h.editor(wire)
            h.callback = {
                h.callback = nil
                if cancel { state.cancelPreview() }
                else { try? state.selectTitle(true) }
            }
            #expect(throws: PreviewFailure.retired) { try state.preparePreview() }
            #expect(await wire.calls.isEmpty)
            #expect(state.display()?.status == (cancel ? .unknown : .editing))
        }
    }
}
