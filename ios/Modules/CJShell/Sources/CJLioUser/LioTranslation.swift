import Foundation

enum LioTranslationLanguage: String, CaseIterable, Codable, Sendable {
    case english = "en-US"
    case chinese = "zh-CN"

    var locale: Locale.Language { Locale.Language(identifier: rawValue) }
}

struct LioTranslationRequest: Sendable {
    let source: LioTranslationLanguage
    let target: LioTranslationLanguage
    let text: [String]
}

enum LioTranslationFailure: Error, Equatable, Sendable {
    case network, quota, service, unsupported, unavailableLocally
    case accessDenied, alreadyAccepted, tooLong, noRecognizedText, unreadableImage
    case speechDenied, speechUnavailable
}

struct LioTranslationResult: Equatable, Sendable {
    let text: [String]
    let offline: Bool
}

@MainActor
struct LioTranslator {
    typealias Operation = @MainActor (LioTranslationRequest) async throws -> [String]
    let remote: Operation?
    let local: Operation

    func translate(_ request: LioTranslationRequest) async throws -> LioTranslationResult {
        if let remote {
            do {
                let text = try await remote(request)
                try Task.checkCancellation()
                guard text.count == request.text.count else { throw LioTranslationFailure.service }
                return .init(text: text, offline: false)
            } catch LioTranslationFailure.network {
            } catch LioTranslationFailure.quota {
            } catch LioTranslationFailure.service {
            }
        }
        try Task.checkCancellation()
        let text = try await local(request)
        try Task.checkCancellation()
        return .init(text: text, offline: true)
    }
}

struct LioRecentTranslation: Codable, Equatable, Identifiable {
    var id = UUID()
    let source: LioTranslationLanguage
    let target: LioTranslationLanguage
    let input: String
    let output: String
    let offline: Bool
}

@MainActor public struct LioTranslationHistory {
    public static let fileName = "translation-recent.json"
    private let directory: URL
    private let isCurrent: @MainActor () -> Bool
    private var file: URL { directory.appendingPathComponent(Self.fileName) }

    public init(directory: URL, isCurrent: @escaping @MainActor () -> Bool) {
        self.directory = directory
        self.isCurrent = isCurrent
    }

    init(directory: URL) {
        self.init(directory: directory, isCurrent: { true })
    }

    private func requireCurrent() throws {
        guard isCurrent() else { throw CancellationError() }
    }

    func load() throws -> [LioRecentTranslation] {
        try requireCurrent()
        do {
            return try JSONDecoder().decode([LioRecentTranslation].self, from: Data(contentsOf: file))
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return []
        }
    }

    func record(_ entry: LioRecentTranslation) throws -> [LioRecentTranslation] {
        let entries = try Array(([entry] + load()).prefix(20))
        try save(entries)
        return entries
    }

    func save(_ entries: [LioRecentTranslation]) throws {
        try requireCurrent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        let data = try JSONEncoder().encode(Array(entries.prefix(20)))
        var savedFile = file
        try data.write(to: savedFile, options: [.atomic, .completeFileProtection])
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: savedFile.path)
        var backup = URLResourceValues()
        backup.isExcludedFromBackup = true
        try savedFile.setResourceValues(backup)
    }

    func clear() throws {
        try requireCurrent()
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
        }
    }
}
