import Foundation

/// Which feedback lines (an answer's message and the exact text) the server has confirmed, for as long as the home
/// screen lives. A confirmed line is removed from the device (#1855), so after the app comes back and the feedback host
/// is made again, nothing saved there says it arrived; this does, so a retry for such a line is answered here and the
/// same words are never sent again under a new ID.
@MainActor final class LioFeedbackLedger {
    private struct Line: Hashable {
        let messageID: String
        let text: String
    }
    private var confirmed: Set<Line> = []

    func record(messageID: String, text: String) { confirmed.insert(Line(messageID: messageID, text: text)) }

    func contains(messageID: String, text: String) -> Bool {
        confirmed.contains(Line(messageID: messageID, text: text))
    }
}
