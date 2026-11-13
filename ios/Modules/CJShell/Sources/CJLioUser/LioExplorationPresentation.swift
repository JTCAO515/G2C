/// Display values produced after the accepted message boundary has validated the snapshot.
/// None of these values enable a protocol or grant write authority.
struct LioExplorationPresentation: Equatable, Sendable {
    struct Segment: Equatable, Sendable {
        enum Purpose: Sendable { case response, direction, question, notice, summary }
        let purpose: Purpose
        let text: String
    }

    struct ProfileEntry: Equatable, Sendable, Identifiable {
        enum State: Sendable { case known, notNeeded, inferred, defaultValue, memory }
        let id: String
        let displayText: String
        let state: State

        func annotation(_ language: LioLanguage) -> String? {
            switch state {
            case .known: nil
            case .notNeeded: language.text("No preference", "都可以")
            case .inferred: language.text("My understanding", "我的理解")
            case .defaultValue: language.text("For now", "暂按这个安排")
            case .memory: language.text("Earlier preference", "之前的偏好")
            }
        }
    }

    struct Notice: Equatable, Sendable, Identifiable {
        enum Severity: Sendable { case info, warning }
        let id: String
        let text: String
        let severity: Severity
        let source: LioSource
    }

    struct Exit: Equatable, Sendable, Identifiable {
        let id: String
        let displayText: String
        let sendText: String
    }

    let segments: [Segment]
    let profile: [ProfileEntry]
    let notices: [Notice]
    let exits: [Exit]
    let answer: String

    /// `answer` is the compatibility projection. Never repeat it below structured body sections.
    /// Profile changes alone do not replace an existing plain answer.
    func plainAnswer(questionCount: Int) -> String? {
        guard segments.isEmpty, questionCount == 0, notices.isEmpty, exits.isEmpty, !answer.isEmpty else { return nil }
        return answer
    }
}
