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

struct LioTranslationHistory {
    let directory: URL
    private var file: URL { directory.appendingPathComponent("recent.json") }

    func load() throws -> [LioRecentTranslation] {
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
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        var localDirectory = directory
        var protection = URLResourceValues()
        protection.isExcludedFromBackup = true
        try localDirectory.setResourceValues(protection)
        let data = try JSONEncoder().encode(Array(entries.prefix(20)))
        try data.write(to: file, options: [.atomic, .completeFileProtection])
    }

    func clear() throws {
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
        }
    }
}
