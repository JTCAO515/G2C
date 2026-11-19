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
