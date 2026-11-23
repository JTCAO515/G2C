import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LocalSupportDraftTests {
    @Test func changesSurviveARecreatedEditorAndClearRemovesTheDraft() {
        var stored: String?
        let storage = LocalSupportDraftStorage(load: { stored }, save: { stored = $0 }, clear: { stored = nil })
        let first = LocalSupportDraft(storage: storage)
        first.load()
        first.edit("第一行\nSecond line")
        let second = LocalSupportDraft(storage: storage)
        second.load()
        #expect(second.text == "第一行\nSecond line")
        second.clear()
        #expect(second.text.isEmpty)
        #expect(stored == nil)
    }

    @Test func excessCharactersKeepTheLastSavedDraft() {
        var stored: String?
        let storage = LocalSupportDraftStorage(load: { stored }, save: { stored = $0 }, clear: { stored = nil })
        let draft = LocalSupportDraft(storage: storage)
        draft.load()
        let maximum = String(repeating: "旅", count: 1000)
        draft.edit(maximum)
        draft.edit(maximum + "人")
        #expect(draft.text == maximum)
        #expect(stored == maximum)
        #expect(draft.problem == .tooLong)
    }

    @Test func loadFailureDoesNotOverwriteStoredData() {
        struct Unavailable: Error {}
        var writes = 0
        let storage = LocalSupportDraftStorage(load: { throw Unavailable() },
                                               save: { _ in writes += 1 }, clear: {})
        let draft = LocalSupportDraft(storage: storage)
        draft.load()
        draft.edit("test")
        #expect(!draft.canEdit)
        #expect(draft.problem == .cannotLoad)
        #expect(writes == 0)
    }
}
