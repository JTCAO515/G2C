import Foundation

/// Display groups for saved memories (#2002). Presentation only: the group comes from the slot string the service
/// stored with the item, never from the memory text, and a slot this app does not know falls into `.other`.
/// Nothing here reads or writes a memory.
enum LioMemoryCategory: String, CaseIterable, Hashable, Sendable {
    case food, pace, budget, lodging, interests, companions, transport, language, other

    /// Slots the service writes today are `diet.*`, `travel.pace`, `travel.budget`, `lodging.style`,
    /// `travel.interests` and `quiet.entrance` (backend `lio_memory_preferences.py`); the rest are the groups
    /// the 58.1 plan names, so a later slot lands in the right place without an App change.
    private static let exact: [String: Self] = [
        "travel.pace": .pace, "travel.budget": .budget, "travel.interests": .interests,
        "travel.companions": .companions, "travel.transport": .transport, "travel.mobility": .transport,
        "profile.language": .language
    ]
    private static let prefixes: [String: Self] = [
        "diet": .food, "food": .food, "cuisine": .food,
        "pace": .pace, "budget": .budget,
        "lodging": .lodging, "hotel": .lodging, "stay": .lodging,
        "interest": .interests, "interests": .interests,
        "companion": .companions, "companions": .companions,
        "transport": .transport, "mobility": .transport,
        "language": .language
    ]

    init(slot: String) {
        let key = slot.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if let match = Self.exact[key] {
            self = match
        } else if let head = key.split(separator: ".").first, let match = Self.prefixes[String(head)] {
            self = match
        } else {
            self = .other
        }
    }

    /// Reading order on the page. `.other` is always last.
    static let order: [Self] = allCases

    /// Chinese and English names for the seven plan groups come from `codex-inbox/G4/ui-copy.json`
    /// (`memory.group.*`). Lodging and Other are not in that file yet, so those two are placeholders.
    func title(_ language: ShellLanguage) -> String {
        switch self {
        case .food: language.text("Food preferences", "饮食")
        case .pace: language.text("Travel pace", "节奏")
        case .budget: language.text("Budget", "预算")
        case .lodging: language.text("Lodging", "住宿")
        case .interests: language.text("Interests", "兴趣")
        case .companions: language.text("Travel companions", "同行")
        case .transport: language.text("Transport preferences", "出行方式")
        case .language: language.text("Language", "语言")
        case .other: language.text("Other", "其他")
        }
    }

    var symbol: String {
        switch self {
        case .food: "fork.knife"
        case .pace: "figure.walk"
        case .budget: "banknote"
        case .lodging: "bed.double"
        case .interests: "star"
        case .companions: "person.2"
        case .transport: "tram"
        case .language: "character.bubble"
        case .other: "bookmark"
        }
    }
}

struct LioMemoryGroup<Element>: Identifiable {
    let category: LioMemoryCategory
    let items: [Element]
    var id: LioMemoryCategory { category }
}

enum LioMemoryGrouping {
    /// Non-empty groups in page order. Items keep the order they arrived in inside their group.
    static func groups<Element>(_ items: [Element], slot: (Element) -> String) -> [LioMemoryGroup<Element>] {
        var buckets: [LioMemoryCategory: [Element]] = [:]
        for item in items { buckets[LioMemoryCategory(slot: slot(item)), default: []].append(item) }
        return LioMemoryCategory.order.compactMap { category in
            buckets[category].map { LioMemoryGroup(category: category, items: $0) }
        }
    }
}

/// Words on the memory page that are not data: what Lio remembers, how to trigger it, where an item came from.
/// Copy for the page title, description, empty title and empty description is from `ui-copy.json`
/// (`memory.page.*`, `memory.empty.*`, `memory.applied.description`); the rest is placeholder copy.
enum LioMemoryCopy {
    static func pageTitle(_ language: ShellLanguage) -> String { language.text("My memories", "我的记忆") }

    static func pageDescription(_ language: ShellLanguage) -> String {
        language.text("Edit, pause, or delete a memory anytime.", "你可随时修改、停用或删除记忆。")
    }

    /// Text only. Whether an answer really used a memory is not read from the service here.
    static func usageNote(_ language: ShellLanguage) -> String {
        language.text("When Lio uses a memory in an answer, it says so: “Based on your saved preference…”.",
                      "Lio 在回答里用到记忆时，会标注「按你记住的…」。")
    }

    static func emptyTitle(_ language: ShellLanguage) -> String { language.text("No memories yet", "还没有记忆") }

    static func emptyDescription(_ language: ShellLanguage) -> String {
        language.text("Share a preference in chat, then tap Remember when Lio suggests it.",
                      "聊天时说出偏好，看到建议就点「记住」。")
    }

    static func remembersHeading(_ language: ShellLanguage) -> String {
        language.text("What Lio can remember", "Lio 会记住什么")
    }

    static func remembers(_ language: ShellLanguage) -> String {
        language.text("Travel pace, budget, lodging style, interests, and food tastes.",
                      "旅行节奏、预算、住宿风格、兴趣和饮食口味。")
    }

    static func examplesHeading(_ language: ShellLanguage) -> String { language.text("Try telling Lio", "试着对 Lio 说") }

    /// Whole sentences the service accepts (backend `lio_memory_preferences.py`, `_FORMS`, after it strips the
    /// leading "remember"). Only conservative wording is listed: each is a complete statement of one supported
    /// preference with no question in it.
    static func examples(_ language: ShellLanguage) -> [String] {
        switch language {
        case .english: ["Remember I like museums", "Remember I prefer slow-paced trips", "Remember I avoid spicy food"]
        case .chinese: ["记住我不吃辣", "记住我喜欢慢节奏的旅行", "记住我喜欢博物馆"]
        }
    }

    static func examplesTip(_ language: ShellLanguage) -> String {
        language.text("Send it as its own message, not mixed with a question. Nothing is saved until you tap Remember.",
                      "单独发一句偏好，别和提问写在同一条里。点「记住」之后才会保存。")
    }

    /// "Saved on …" and the source, on one line.
    static func summary(recordedAt: Date, longTerm: Bool, language: ShellLanguage,
                        timeZone: TimeZone = .current) -> String {
        let source = sourceText(longTerm: longTerm, language: language)
        return "\(savedOn(recordedAt, language: language, timeZone: timeZone)) · \(source)"
    }

    static func sourceText(longTerm: Bool, language: ShellLanguage) -> String {
        longTerm ? language.text("Source: you asked Lio to remember it", "来源：你让 Lio 记住的")
                 : language.text("Source: this trip’s chat", "来源：这次行程的对话")
    }

    static func savedOn(_ recordedAt: Date, language: ShellLanguage, timeZone: TimeZone = .current) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: language == .english ? "en" : "zh-Hans")
        formatter.timeZone = timeZone
        formatter.dateStyle = .medium
        formatter.timeStyle = .none
        let text = formatter.string(from: recordedAt)
        return language.text("Saved on \(text)", "记于\(text)")
    }
}
