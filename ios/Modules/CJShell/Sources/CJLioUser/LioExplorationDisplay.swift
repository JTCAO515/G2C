import CJMessageHTTP

/// A public-display projection, not admission to a new timeline or a send capability.
struct LioExplorationDisplay {
    let messageID: String
    let presentation: LioExplorationPresentation
    let questions: [LioQuestionGroup]
    let state: LioTimelineWire.Message.State
    let progress: LioExplorationWire.Progress?

    init(_ message: LioExplorationWire.Message) throws {
        var visible = [message.answer]
        visible += message.segments.map(\.text)
        visible += message.profile.map(\.displayText)
        visible += message.notices.map(\.text)
        visible += message.exits.flatMap { [$0.displayText, $0.sendText] }
        visible += message.questions.flatMap { [$0.question] + $0.options.flatMap { [$0.displayText, $0.sendText] } }
        guard visible.allSatisfy(LioPublicDisplay.permitsText) else { throw LioExplorationDisplayFailure.unavailable }
        let segments = message.segments.map { segment -> LioExplorationPresentation.Segment in
            let purpose: LioExplorationPresentation.Segment.Purpose
            switch segment.purpose { case .response: purpose = .response; case .direction: purpose = .direction
            case .question: purpose = .question; case .notice: purpose = .notice; case .summary: purpose = .summary }
            return .init(purpose: purpose, text: segment.text)
        }
        let profile = message.profile.map { item -> LioExplorationPresentation.ProfileEntry in
            let state: LioExplorationPresentation.ProfileEntry.State
            switch item.state { case .known: state = .known; case .notNeeded: state = .notNeeded
            case .inferred: state = .inferred; case .defaultValue: state = .defaultValue; case .memory: state = .memory }
            return .init(id: item.factor, displayText: item.displayText, state: state)
        }
        let notices = message.notices.map { item -> LioExplorationPresentation.Notice in
            let url = item.source.link.flatMap { LioPublicDisplay.permitsSource($0) ? $0 : nil }
            return .init(id: item.id, text: item.text, severity: item.severity == .warning ? .warning : .info,
                         source: LioSource(id: item.id, title: item.source.title, url: url))
        }
        messageID = message.id
        presentation = .init(segments: segments, profile: profile, notices: notices,
                             exits: message.exits.map { .init(id: $0.id, displayText: $0.displayText, sendText: $0.sendText) },
                             answer: message.answer)
        questions = message.questions.map { group in
            LioQuestionGroup(id: group.factor, question: group.question, multiple: group.multiple,
                             options: group.options.map { .init(id: $0.id, displayText: $0.displayText, sendText: $0.sendText) })
        }
        state = message.state
        progress = message.progress
    }

    /// Old message and plain-text behavior stays explicit; no retagging or inferred new fields.
    init(legacy message: LioTimelineWire.Message) throws {
        guard LioPublicDisplay.permitsText(message.answer) else { throw LioExplorationDisplayFailure.unavailable }
        messageID = message.id
        presentation = .init(segments: [], profile: [], notices: [], exits: [], answer: message.answer)
        questions = []
        state = message.state
        progress = nil
    }

    func draft() -> LioQuestionDraft { LioQuestionDraft(messageID: messageID, questions: questions) }
}

enum LioExplorationDisplayFailure: Error { case unavailable }
