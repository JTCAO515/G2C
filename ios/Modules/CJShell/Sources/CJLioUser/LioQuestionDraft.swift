/// Presentation values made from validated question groups. They do not admit a new wire version.
struct LioQuestionOption: Equatable, Sendable, Identifiable {
    let id: String
    let displayText: String
    let sendText: String
}

struct LioQuestionGroup: Equatable, Sendable, Identifiable {
    let id: String
    let question: String
    let multiple: Bool
    let options: [LioQuestionOption]
}

/// The parent owns this value alongside its conversation, rather than inside a transient row.
struct LioQuestionDraft: Equatable, Sendable {
    private(set) var messageID: String
    private(set) var questions: [LioQuestionGroup]
    private var selections: [String: Set<String>] = [:]

    init(messageID: String, questions: [LioQuestionGroup]) {
        self.messageID = messageID
        self.questions = questions
    }

    func isSelected(_ option: LioQuestionOption, in question: LioQuestionGroup) -> Bool {
        selections[question.id, default: []].contains(option.id)
    }

    mutating func toggle(_ option: LioQuestionOption, in question: LioQuestionGroup) {
        if isSelected(option, in: question) {
            selections[question.id, default: []].remove(option.id)
        } else if question.multiple {
            selections[question.id, default: []].insert(option.id)
        } else {
            selections[question.id] = [option.id]
        }
    }

    /// Partial answers are allowed; order comes from the complete snapshot, not tap order.
    var jointReply: String {
        questions.flatMap { question in
            question.options.filter { isSelected($0, in: question) }.map(\.sendText)
        }.joined(separator: "\n")
    }

    /// An unchanged group keeps its choices. A replaced group or message starts fresh.
    mutating func apply(messageID: String, questions: [LioQuestionGroup]) {
        if self.messageID == messageID {
            let unchanged = Set(questions.filter { self.questions.contains($0) }.map(\.id))
            selections = selections.filter { unchanged.contains($0.key) }
        } else {
            selections = [:]
        }
        self.messageID = messageID
        self.questions = questions
    }
}
