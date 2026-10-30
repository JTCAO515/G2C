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

public enum TripRoute: Hashable, Sendable { case detail, proposal, originalAction }

public enum MemoryRoute: Hashable, Sendable {
    case group(MemoryGroup)
    case account, language, help, privacy, support
    case memoryItems, memoryDetail, manualMemory, memoryActions
    case feedback(FeedbackContainerEntry?)
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

/// UI-local opaque generation, not a principal, session ID or authentication proof.
public struct ShellGeneration: Equatable, Sendable {
    fileprivate let value = UUID()
    fileprivate init() {}
}

public struct ShellPresentation: Equatable, Sendable {
    public var context: ShellContext
    public var assistantBody: String?
    public var assistant: ShellPageState
    public var trips: ShellPageState
    public var memory: ShellPageState
    public init(context: ShellContext = ShellContext(), assistantBody: String? = nil,
                assistant: ShellPageState = .notConnected, trips: ShellPageState = .notConnected,
                memory: ShellPageState = .notConnected) {
        self.context = context
        self.assistantBody = assistantBody
        self.assistant = assistant
        self.trips = trips
        self.memory = memory
    }
}

@MainActor @Observable
public final class ShellState {
    public static let contractVersion = "UI@1.1"
    public static let languageKey = "cj.ui.language.v1"
    public var selectedTab: ShellTab = .assistant
    public var tripPath: [TripRoute] = []
    public var memoryPath: [MemoryRoute] = []
    public private(set) var draftRevision = UUID()
    public var draft = "" { didSet { draftRevision = UUID() } }
    var messageBindingBlocked = false
    @ObservationIgnored weak var originalUsageContainerHost: OriginalUsageContainerHost?
    @ObservationIgnored weak var usageContainerHost: UsageContainerHost?
    @ObservationIgnored weak var runContainerHost: RunContainerHost?
    @ObservationIgnored weak var answerFeedbackHost: FeedbackContainerHost?
    @ObservationIgnored weak var generalFeedbackHost: FeedbackContainerHost?
    @ObservationIgnored weak var needsContainerHost: NeedsContainerHost?
    @ObservationIgnored weak var tripContainerHost: TripContainerHost?
    @ObservationIgnored weak var memoryContainerHost: MemoryContainerHost?
    @ObservationIgnored weak var typedMemoryContainerHost: TypedMemoryContainerHost?
    @ObservationIgnored weak var serverHistoryHost: ServerHistoryHost?
    @ObservationIgnored weak var messageHost: AssistantMessageHost?
    public private(set) var generation = ShellGeneration()
    /// Local displayed-answer revision only; the trusted root supplies actual message/run references.
    public private(set) var assistantContentRevision = UUID()
    public private(set) var presentation = ShellPresentation()
    public var context: ShellContext { presentation.context }
    public var assistantBody: String? { presentation.assistantBody }
    public var assistantState: ShellPageState { presentation.assistant }
    public var tripsState: ShellPageState { presentation.trips }
    public var memoryState: ShellPageState { presentation.memory }
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

    /// Host calls synchronously before changing identity or accepting new account work.
    /// This only clears local UI; it does not revoke credentials or cancel remote work.
    @discardableResult public func invalidateIdentity() -> ShellGeneration {
        let invalidatedGeneration = ShellGeneration()
        messageBindingBlocked = true
        generation = invalidatedGeneration
        draft = ""
        contextReset()
        // Publish the fence and clear private UI before a resource callback can reenter.
        // No outer-lifetime mutation is allowed after this callback.
        originalUsageContainerHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        usageContainerHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        runContainerHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        answerFeedbackHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        generalFeedbackHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        needsContainerHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        tripContainerHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        memoryContainerHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        typedMemoryContainerHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        serverHistoryHost?.invalidate()
        guard generation == invalidatedGeneration else { return invalidatedGeneration }
        messageHost?.invalidate()
        return invalidatedGeneration
    }

    private func contextReset() {
        memoryPath = []; tripPath = []
        assistantContentRevision = UUID()
        presentation = ShellPresentation()
    }

    /// Capture generation before work, retain it across awaits, and apply only here.
    /// An old instance's generation is also rejected. Caller remains responsible for auth.
    @discardableResult
    public func apply(_ value: ShellPresentation, for capturedGeneration: ShellGeneration) -> Bool {
        guard generation == capturedGeneration else { return false }
        // Every new displayed presentation retires the old answer-feedback association.
        // General feedback remains independent. The root may bind the new actual references afterward.
        answerFeedbackHost?.invalidate()
        guard generation == capturedGeneration else { return false }
        assistantContentRevision = UUID()
        presentation = value
        return true
    }

    public var hasDraft: Bool { !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    // MESSAGE/RUN are not consumed. No method clears a draft or pretends to send.
    public var canSend: Bool { false }
}
