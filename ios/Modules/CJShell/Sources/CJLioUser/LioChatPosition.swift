import CJMessageClient
import Foundation

extension LioChatContinuity {
    /// Navigation metadata only. Original submissions remain in their existing journal.
    public func encodedPosition() throws -> Data {
        try JSONEncoder().encode(StoredChatPosition(self))
    }

    /// Restore a complete record before attaching its writer. Invalid data leaves this instance intact.
    public func restorePosition(_ bytes: Data) throws {
        guard bytes.count <= 1_048_576 else { throw RecoveryError.invalidSnapshot }
        let record: StoredChatPosition
        do { record = try JSONDecoder().decode(StoredChatPosition.self, from: bytes) }
        catch is DecodingError { throw RecoveryError.invalidSnapshot }
        guard record.format == 1, record.hasValidIdentifiers else { throw RecoveryError.invalidSnapshot }
        let questions = record.questions.mapValues { $0.question }
        withPositionChange {
            selectedID = record.selected
            draft = record.draft
            drafts = record.drafts
            firstQuestions = questions
            localIDs = record.bindings
            blankIDs = record.blanks
        }
    }
}

private struct StoredChatPosition: Codable {
    let format: Int
    let selected: Data?
    let draft: String
    let drafts: [Data: String]
    let questions: [Data: StoredFirstQuestion]
    let bindings: [Data: String]
    let blanks: Set<Data>

    @MainActor init(_ position: LioChatContinuity) {
        format = 1; selected = position.selectedID; draft = position.draft; drafts = position.drafts
        questions = position.firstQuestions.mapValues(StoredFirstQuestion.init)
        bindings = position.localIDs; blanks = position.blankIDs
    }

    var hasValidIdentifiers: Bool {
        func valid(_ bytes: Data) -> Bool {
            !bytes.isEmpty && bytes.count <= 1024 && !bytes.contains(0) && String(data: bytes, encoding: .utf8) != nil
        }
        return selected.map(valid) != false && blanks.allSatisfy(valid) && drafts.keys.allSatisfy(valid)
            && questions.allSatisfy { valid($0.key) && valid(Data($0.value.messageID.utf8)) }
            && bindings.allSatisfy { valid($0.key) && valid(Data($0.value.utf8)) }
    }
}
private struct StoredFirstQuestion: Codable {
    enum Language: String, Codable { case english = "en", chinese = "zh" }
    let messageID: String
    let text: String
    let language: Language
    let isResend: Bool
    init(_ question: LioQuestion) {
        messageID = question.messageID; text = question.text
        language = question.language == .chinese ? .chinese : .english
        isResend = question.isResend
    }
    var question: LioQuestion {
        .init(messageID: messageID, text: text, language: language == .chinese ? .chinese : .english, isResend: isResend)
    }
}
