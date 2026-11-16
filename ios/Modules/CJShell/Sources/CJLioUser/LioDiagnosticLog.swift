import CJMessageHTTP
import Foundation

/// Bounded problem notes kept only on this device and never sent anywhere.
/// An entry holds a category, stage, request kind, HTTP status, the service's request
/// reference, time and build; it has no field for tokens, invitation codes, account or
/// conversation identifiers, or message text.
@MainActor public final class LioDiagnosticLog {
    public struct Entry: Codable, Sendable, Equatable {
        public let category: LioFailureDiagnosis.Category
        public let stage: LioFailureDiagnosis.Stage
        public let request: String?
        public let httpStatus: Int?
        public let reference: String?
        public let time: Date
        public let build: String
        public let origin: LioFailureDiagnosis.Stage?
        public let cause: LioProblemCause?
        public let errorCode: Int?
    }

    public static let limit = 20
    /// Repeated identical failures (for example timeline polling) are kept once per window.
    static let repeatWindow: TimeInterval = 60

    public static let shared = LioDiagnosticLog(
        defaults: .standard,
        build: Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?")

    private let defaults: UserDefaults
    private let key: String
    private let build: String
    public private(set) var entries: [Entry]

    init(defaults: UserDefaults, key: String = "g2c.lio.problem-notes.v1", build: String) {
        self.defaults = defaults
        self.key = key
        self.build = build
        // Notes are advisory; unreadable saved notes start an empty list instead of failing a screen.
        let saved = defaults.data(forKey: key).flatMap { try? JSONDecoder().decode([Entry].self, from: $0) } ?? []
        entries = Array(saved.prefix(Self.limit))
    }

    public func record(_ diagnosis: LioFailureDiagnosis, at time: Date = Date()) {
        store(diagnosis, problem: nil, at: time)
    }

    public func record(error: any Error, stage: LioFailureDiagnosis.Stage,
                       observation: LioTimelineHTTP.Observation? = nil, at time: Date = Date()) {
        record(LioRequestProblem(error, stage: stage, observation: observation), at: time)
    }

    func record(_ problem: LioRequestProblem, at time: Date = Date()) {
        store(problem.diagnosis, problem: problem, at: time)
    }

    private func store(_ diagnosis: LioFailureDiagnosis, problem: LioRequestProblem?, at time: Date) {
        let entry = Entry(category: diagnosis.category, stage: diagnosis.stage,
                          request: diagnosis.request.map(Self.code), httpStatus: diagnosis.httpStatus,
                          reference: diagnosis.serverReference, time: time, build: build,
                          origin: problem?.origin, cause: problem?.cause, errorCode: problem?.errorCode)
        if let latest = entries.first, latest.category == entry.category, latest.stage == entry.stage,
           latest.request == entry.request, latest.httpStatus == entry.httpStatus,
           latest.reference == entry.reference, latest.origin == entry.origin, latest.cause == entry.cause,
           latest.errorCode == entry.errorCode,
           abs(time.timeIntervalSince(latest.time)) < Self.repeatWindow { return }
        entries.insert(entry, at: 0)
        if entries.count > Self.limit { entries.removeLast(entries.count - Self.limit) }
        if let data = try? JSONEncoder().encode(entries) { defaults.set(data, forKey: key) }
    }

    static func code(_ kind: LioTimelineHTTP.RequestKind) -> String {
        switch kind {
        case .send: "send"
        case .sessionCheck: "session-check"
        case .firstLookup: "first-send-lookup"
        case .timeline: "timeline"
        case .exploration: "exploration"
        case .tripHistory: "trip-history"
        case .undo: "undo"
        case .memoryChoice: "memory-choice"
        }
    }

    /// Plain lines for a screenshot or copy; English codes keep notes comparable across languages.
    public func text(_ language: LioLanguage) -> String {
        guard !entries.isEmpty else { return language.text("No problems noted.", "暂无问题记录。") }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = .current
        return entries.map { entry in
            var fields = [formatter.string(from: entry.time), language.text("build", "构建") + " " + entry.build,
             entry.category.rawValue, entry.stage.rawValue, entry.request ?? "-",
             "HTTP " + (entry.httpStatus.map(String.init) ?? "-"),
             "ref " + (entry.reference ?? "-")]
            if let origin = entry.origin { fields.append("origin=" + origin.rawValue) }
            if let cause = entry.cause { fields.append("cause=" + cause.rawValue) }
            if let code = entry.errorCode { fields.append("error=" + String(code)) }
            return fields.joined(separator: " · ")
        }.joined(separator: "\n")
    }
}
