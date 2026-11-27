import Foundation

/// What happens when a traveller taps one of the 「去办」 chips (#1979): its sentence goes to Lio as a question, the
/// same way a typed one does. The chat's own rules (consent, a reply already on its way, the app being in the
/// foreground) can refuse it; the sentence is then left in the message box so the tap is not lost, unless the
/// traveller already has something typed there, which is never overwritten.
enum LioTodoChipAsk {
    enum Outcome: Equatable {
        /// The chat took it as a question.
        case sent
        /// The chat did not take it: put it in the message box.
        case draft(String)
        /// The chat did not take it and the message box has the traveller's own text: leave both as they are.
        case kept
    }

    /// `send` is the chat's send path and says whether it took the question.
    static func run(_ sentence: String, currentDraft: String, send: (String) -> Bool) -> Outcome {
        let text = sentence.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return .kept }
        if send(text) { return .sent }
        return currentDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? .draft(text) : .kept
    }
}
