import Darwin
import Foundation

enum LioTranslationLanguage: String, CaseIterable, Codable, Sendable {
    case english = "en-US"
    case chinese = "zh-CN"
}

struct LioTranslationRequest: Sendable {
    let source: LioTranslationLanguage
    let target: LioTranslationLanguage
    let text: [String]
}

enum LioTranslationFailure: Error, Equatable, Sendable {
    case network, quota, service, timedOut
    case signInRequired, accessDenied, alreadyAccepted, tooLong, noRecognizedText, noRecognizedTextInPhoto, unreadableImage
    case invalidRecording

    static func emptyResult(for kind: LioRelayTranslationRequest.Kind) -> Self {
        kind == .image ? .noRecognizedTextInPhoto : .noRecognizedText
    }
}

struct LioTranslationResult: Equatable, Sendable {
    let text: [String]
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
    public static let directoryName = "translation-history"
    public static let fileName = "recent.json"
    public static let relayOriginalsFileName = "relay-originals.json"
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
        let data = try JSONEncoder().encode(Array(entries.prefix(20)))
        try protectedWrite(data, to: file)
    }

    func loadRelayOriginals() throws -> Data? {
        try requireCurrent()
        let path = directory.appendingPathComponent(Self.relayOriginalsFileName)
        do { return try Data(contentsOf: path) }
        catch let error as CocoaError where error.code == .fileReadNoSuchFile { return nil }
    }

    func saveRelayOriginals(_ data: Data) throws {
        try protectedWrite(data, to: directory.appendingPathComponent(Self.relayOriginalsFileName))
    }

    private func protectedWrite(_ data: Data, to destination: URL) throws {
        try requireCurrent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: 0o700])
        var localDirectory = directory
        var backup = URLResourceValues()
        backup.isExcludedFromBackup = true
        try localDirectory.setResourceValues(backup)
        try data.write(to: destination, options: [.atomic, .completeFileProtection])
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path)
        try sync(destination, access: O_RDWR)
        try sync(directory, access: O_RDONLY | O_DIRECTORY)
        try sync(directory.deletingLastPathComponent(), access: O_RDONLY | O_DIRECTORY)
    }

    private func sync(_ path: URL, access: Int32) throws {
        let descriptor = open(path.path, access | O_NOFOLLOW | O_CLOEXEC)
        guard descriptor >= 0 else { throw CocoaError(.fileWriteUnknown) }
        defer { close(descriptor) }
        guard fsync(descriptor) == 0 else { throw CocoaError(.fileWriteUnknown) }
    }

    func clear() throws {
        try requireCurrent()
        do {
            try FileManager.default.removeItem(at: file)
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
        }
    }
}
