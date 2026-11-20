import Foundation
import Testing
@testable import CJLioUser

@MainActor
struct LioTranslationTests {
    @Test func recentTranslationsSurviveReopeningAndCanBeCleared() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let history = LioTranslationHistory(directory: directory)
        let item = LioRecentTranslation(source: .english, target: .chinese,
                                        input: "Hello", output: "你好", offline: true)
        try history.save([item])
        #expect(try LioTranslationHistory(directory: directory).load() == [item])
        try history.clear()
        #expect(try LioTranslationHistory(directory: directory).load().isEmpty)
    }

    @Test func recordingDoesNotOverwriteUnreadableHistory() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent(LioTranslationHistory.fileName)
        let original = Data("invalid saved data".utf8)
        try original.write(to: file)
        let history = LioTranslationHistory(directory: directory)
        let item = LioRecentTranslation(source: .english, target: .chinese,
                                        input: "Hello", output: "你好", offline: true)
        #expect(throws: DecodingError.self) { try history.record(item) }
        #expect(try Data(contentsOf: file) == original)
    }

    @Test func retiredAccountCannotRecreateTranslationHistory() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let history = LioTranslationHistory(directory: directory, isCurrent: { current })
        let item = LioRecentTranslation(source: .english, target: .chinese,
                                        input: "Hello", output: "你好", offline: true)
        try history.save([item])
        try history.clear()
        current = false
        #expect(throws: CancellationError.self) { try history.record(item) }
        #expect(throws: CancellationError.self) { try history.load() }
        #expect(throws: CancellationError.self) { try history.clear() }
        #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).isEmpty)
    }
}
