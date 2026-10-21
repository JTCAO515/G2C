import Foundation
import Observation

public enum ShellLanguage: String, CaseIterable, Codable, Sendable {
    case english = "en"
    case chinese = "zh-Hans"

    public func text(_ english: String, _ chinese: String) -> String {
        self == .english ? english : chinese
    }
}

public enum ShellTab: String, CaseIterable, Codable, Sendable {
    case assistant, trips, plugins, memory

    public func title(_ language: ShellLanguage) -> String {
        switch self {
        case .assistant: language.text("Assistant", "助手")
        case .trips: language.text("Trips", "行程")
        case .plugins: language.text("Plugins", "插件")
        case .memory: language.text("Memory", "记忆")
        }
    }
}

/// Presentation only. These are not API outcomes, auth states or save receipts.
public enum ShellPageState: String, CaseIterable, Codable, Sendable {
    case notConnected, empty, loading, failed, offline, unknown
}

public enum MemoryGroup: String, CaseIterable, Codable, Sendable {
    case facts, experiences, preferences

    public func title(_ language: ShellLanguage) -> String {
        switch self {
        case .facts: language.text("Facts", "事实")
        case .experiences: language.text("Experiences", "经历")
        case .preferences: language.text("Preferences", "偏好")
        }
    }
}

public enum MemoryRoute: Hashable, Sendable {
    case group(MemoryGroup)
    case account, language, help, privacy, support
}

/// Retained opaquely during UI navigation; never an authority or an ID generator.
/// The domain owner supplies and clears references when identity changes.
public struct ShellContext: Equatable, Sendable {
    public var conversationReference: String?
    public var tripReference: String?
    public init(conversationReference: String? = nil, tripReference: String? = nil) {
        self.conversationReference = conversationReference
        self.tripReference = tripReference
    }
}

@MainActor @Observable
public final class ShellState {
    public static let contractVersion = "UI@1.0"
    public static let languageKey = "cj.ui.language.v1"
    public var selectedTab: ShellTab = .assistant
    public var memoryPath: [MemoryRoute] = []
    public var draft = ""
    public var context = ShellContext()
    public var assistantState: ShellPageState = .notConnected
    public var tripsState: ShellPageState = .notConnected
    public var memoryState: ShellPageState = .notConnected
    public private(set) var language: ShellLanguage
    public private(set) var invalidStoredLanguage = false
    @ObservationIgnored private let preferences: UserDefaults

    public init(preferences: UserDefaults = .standard) {
        self.preferences = preferences
        let stored = preferences.string(forKey: Self.languageKey)
        language = stored.flatMap(ShellLanguage.init(rawValue:)) ?? .english
        invalidStoredLanguage = stored != nil && ShellLanguage(rawValue: stored ?? "") == nil
    }

    public func selectLanguage(_ value: ShellLanguage) {
        preferences.set(value.rawValue, forKey: Self.languageKey)
        language = value
        invalidStoredLanguage = false
    }

    public var hasDraft: Bool { !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    // MESSAGE/RUN are not consumed. No method clears a draft or pretends to send.
    public var canSend: Bool { false }
}
