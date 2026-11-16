import CJMessageClient
import Foundation
import Testing
@testable import CJLioUser

@MainActor struct LioChatPositionTests {
    @Test func duplicateVersionCannotChooseWhichPositionToRestore() throws {
        let source = LioChatContinuity(); source.draft = "Saved draft"
        let valid = try #require(String(data: try source.encodedPosition(), encoding: .utf8))
        for value in ["{\"format\":99," + valid.dropFirst(), String(valid.dropLast()) + ",\"format\":99}"] {
            let current = LioChatContinuity(); current.draft = "Visible draft"
            #expect(throws: RecoveryError.invalidSnapshot) { try current.restorePosition(Data(value.utf8)) }
            #expect(current.draft == "Visible draft")
        }
    }

    @Test func changedDraftIsDurableBeforeTheSetterReturnsAndRetryKeepsItsBytes() throws {
        let position = LioChatContinuity()
        var saved: [Data] = []
        var failing = false
        position.bindPositionWriter { bytes in
            if failing { throw RecoveryError.persistenceUnknown }
            saved.append(bytes)
        }
        position.draft = "  最后输入的草稿\n "
        let first = try #require(saved.last)
        let fresh = LioChatContinuity(); try fresh.restorePosition(first)
        #expect(fresh.draft.utf8.elementsEqual(position.draft.utf8))
        failing = true
        position.draft = "  第二条仍在输入框\n "
        #expect(position.positionIssue != nil)
        #expect(position.draft == "  第二条仍在输入框\n ")
        #expect(saved.count == 1)
        failing = false
        position.retryKeepingPosition()
        #expect(position.positionIssue == nil && saved.count == 2)
        let reopened = LioChatContinuity(); try reopened.restorePosition(try #require(saved.last))
        #expect(reopened.draft.utf8.elementsEqual(position.draft.utf8))
    }

    @Test func inheritingARenewedHostWritesOneCompletePosition() throws {
        let old = LioChatContinuity()
        old.selectedID = Data("synthetic-selected".utf8); old.draft = "Keep this exact draft"
        let current = LioChatContinuity()
        var saved: [Data] = []
        current.bindPositionWriter { saved.append($0) }
        current.inherit(old)
        #expect(saved.count == 1)
        let reopened = LioChatContinuity(); try reopened.restorePosition(try #require(saved.last))
        #expect(reopened.selectedID == old.selectedID && reopened.draft == old.draft)
    }

    @Test func switchingChatsPersistsEachDraftWithItsOwnSelection() throws {
        let a = Data("synthetic-A".utf8), b = Data("synthetic-B".utf8)
        let position = LioChatContinuity()
        position.selectedID = a
        position.updateDraft("A 原草稿", for: a)
        #expect(position.switchChat(to: b, leaving: a, currentDraft: "A 原草稿") == "")
        position.updateDraft("B 原草稿", for: b)
        let cold = LioChatContinuity()
        try cold.restorePosition(position.encodedPosition())
        #expect(cold.selectedID == b && cold.draft == "B 原草稿")
        #expect(cold.switchChat(to: a, leaving: b, currentDraft: cold.draft) == "A 原草稿")
        #expect(cold.drafts[b] == "B 原草稿")
    }

    @Test func coldInstanceRestoresTheSameSelectedChatDraftAndUncertainFirstIdentity() throws {
        let original = LioChatContinuity()
        let selected = Data(UUID().uuidString.utf8)
        original.selectedID = selected
        original.draft = "  北京三天\n luxury hotels  "
        original.blankIDs = [selected]
        let question = LioQuestion(messageID: "original-synthetic-id", text: "  原问题\n ", language: .chinese)
        original.firstQuestions[selected] = question
        let restored = LioChatContinuity()
        try restored.restorePosition(original.encodedPosition())
        #expect(restored.selectedID == original.selectedID)
        #expect(restored.draft.utf8.elementsEqual(original.draft.utf8))
        #expect(restored.firstQuestions[selected] == question)
        #expect(restored.blankIDs == original.blankIDs)
    }
    @Test func verifiedChatBindingAndUnrelatedPendingFirstQuestionBothSurvive() throws {
        let original = LioChatContinuity()
        let local = UUID().uuidString, pending = Data(UUID().uuidString.utf8)
        let server = Data("lio-dialogue-0123456789abcdef0123456789abcdef".utf8)
        original.selectedID = Data(local.utf8)
        original.localIDs[server] = local
        original.firstQuestions[pending] = .init(messageID: "different-pending", text: "Another original", language: .english)
        original.blankIDs = [pending]
        let restored = LioChatContinuity()
        try restored.restorePosition(original.encodedPosition())
        #expect(restored.selectedID == original.selectedID)
        #expect(restored.localIDs == original.localIDs)
        #expect(restored.firstQuestions == original.firstQuestions)
        #expect(restored.blankIDs == original.blankIDs)
    }
    @Test func malformedOrNewerRecordDoesNotClearCurrentPosition() throws {
        let current = LioChatContinuity()
        current.selectedID = Data("synthetic-current".utf8)
        current.draft = "Keep this draft"
        #expect(throws: (any Error).self) { try current.restorePosition(Data("not JSON".utf8)) }
        #expect(current.draft == "Keep this draft")
        #expect(current.selectedID == Data("synthetic-current".utf8))
        let encoded = try current.encodedPosition()
        var value = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        value["format"] = 99
        #expect(throws: RecoveryError.invalidSnapshot) { try current.restorePosition(JSONSerialization.data(withJSONObject: value)) }
        #expect(current.draft == "Keep this draft")
    }
}
