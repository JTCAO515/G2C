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

    @Test func textUsesTheRemoteAnswerWhenAvailable() async throws {
        let translator = LioTranslator(remote: { _ in ["你好"] }, local: { _ in
            Issue.record("The local translator must not run after a remote success")
            return []
        })
        let result = try await translator.translate(.init(source: .english, target: .chinese, text: ["Hello"]))
        #expect(result.text == ["你好"])
        #expect(!result.offline)
    }

    @Test(arguments: [LioTranslationFailure.network, .quota, .service])
    func fallsBackAndLabelsLocalOutput(_ failure: LioTranslationFailure) async throws {
        let translator = LioTranslator(remote: { _ in throw failure }, local: { request in
            #expect(request.text == ["Hello", "Goodbye"])
            return ["你好", "再见"]
        })
        let result = try await translator.translate(.init(source: .english, target: .chinese, text: ["Hello", "Goodbye"]))
        #expect(result.text == ["你好", "再见"])
        #expect(result.offline)
    }

    @Test func reportsAnUnsupportedDeviceWithoutAnInventedTranslation() async {
        let translator = LioTranslator(remote: nil, local: { _ in throw LioTranslationFailure.unsupported })
        await #expect(throws: LioTranslationFailure.unsupported) {
            try await translator.translate(.init(source: .chinese, target: .english, text: ["你好"]))
        }
    }

    @Test nonisolated func missingLanguagePackWithNoConnectionNeverStartsTranslation() async {
        let request = LioTranslationRequest(source: .english, target: .chinese, text: ["Hello"])
        await #expect(throws: LioTranslationFailure.unavailableLocally) {
            try await LioTranslator.translateLocally(request, languagePack: .downloadable, prepare: {
                throw URLError(.notConnectedToInternet)
            }, translate: { _ in
                Issue.record("Translation must wait for both language packs")
                return ""
            })
        }
    }

    @Test nonisolated func alreadyInstalledLanguagesTranslateWithoutADownload() async throws {
        let request = LioTranslationRequest(source: .english, target: .chinese, text: ["Hello", "Tea"])
        let lines = try await LioTranslator.translateLocally(request, languagePack: .installed, prepare: {
            Issue.record("Installed language packs do not need to download")
        }, translate: { $0 == "Hello" ? "你好" : "茶" })
        #expect(lines == ["你好", "茶"])
    }

    @Test func cancellationDoesNotStartLocalTranslation() async {
        let translator = LioTranslator(remote: { _ in throw CancellationError() }, local: { _ in
            Issue.record("Cancellation should stop the request")
            return []
        })
        await #expect(throws: CancellationError.self) {
            try await translator.translate(.init(source: .english, target: .chinese, text: ["Hello"]))
        }
    }
}
