import XCTest
import Foundation

@MainActor final class DevelopmentRunUITests: XCTestCase {
    private let bundle = "space.go2china.run.acceptance"
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private struct Fixture: Decodable {
        let endpoint: String
        let accounts: [String: String]
        let subjects: [String: String]
        let conversation: String
        let prompt: String
        let choice: String
    }
    private struct Proof: Decodable {
        let status: String?
        let text: String
        let effects: Int
        let message_id: String?
        let receipts: Int
        let provider_calls: Int
        let posts: Int
        let cancellations: Int
        let forbidden_writes: Int
    }
    private func call(_ path: String, _ query: [String: String]) async throws -> Data {
        var url = URLComponents(string: control + path)!
        url.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return data
    }
    private func proof(_ fixture: Fixture) async throws -> Proof {
        try JSONDecoder().decode(Proof.self, from: await call("/proof", ["case": fixture.conversation]))
    }
    private func tap(_ identifier: String) {
        let button = app.buttons.matching(identifier: identifier).firstMatch
        _ = button.waitForExistence(timeout: 2)
        let visible = NSPredicate(format: "exists == true AND hittable == true")
        for _ in 0..<14 {
            if visible.evaluate(with: button) { break }
            app.swipeUp()
        }
        XCTAssertTrue(visible.evaluate(with: button), identifier)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 15), .completed, identifier)
        button.tap()
    }
    private func status(_ text: String) {
        let value = app.staticTexts["run.display.status"]
        XCTAssertTrue(value.waitForExistence(timeout: 10))
        let expected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", text), object: value)
        XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 30), .completed, value.label)
    }
    private func launch(_ fixture: Fixture, language: String, restore: Bool = false) throws {
        app?.terminate(); app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": fixture.endpoint,
            "G2C_DEV_TOKEN": "", "G2C_DEV_ACCOUNTS": restore ? "{}" : String(data: try JSONEncoder().encode(fixture.accounts), encoding: .utf8)!]
        app.launch(); XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        tap(language == "en" ? "Memory" : "记忆"); tap("memory.account")
        if restore { tap("account.development.restore") }
        else { tap("account.development.signout"); tap("account.development.signin." + fixture.choice) }
        let signed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", fixture.subjects[fixture.choice]!), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [signed], timeout: 20), .completed)
        tap(language == "en" ? "Assistant" : "助手")
    }
    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }
    private func run(_ mode: String, language: String) async throws {
        continueAfterFailure = false
        defer { app?.terminate() }
        let fixture = try JSONDecoder().decode(Fixture.self, from: await call("/prepare", ["mode": mode, "language": language]))
        try launch(fixture, language: language)
        tap("assistant.serverHistory"); tap("history.loadConversations")
        tap("history.conversation." + fixture.conversation); tap("assistant.panel.done")
        let field = app.textViews["assistant.draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10)); field.tap(); field.typeText(fixture.prompt)
        XCTAssertEqual(field.value as? String, fixture.prompt)
        if app.buttons["Done"].exists { tap("Done") } else if app.buttons["完成"].exists { tap("完成") }
        tap("assistant.send")
        if mode == "failure" {
            status(language == "en" ? "Failed" : "运行失败")
            XCTAssertFalse(app.staticTexts["run.display.text"].exists)
            XCTAssertFalse(app.staticTexts["run.stream.text"].exists)
            let result = try await proof(fixture)
            XCTAssertEqual(result.status, "failed"); XCTAssertEqual(result.text, "")
            XCTAssertEqual(result.provider_calls, 1); XCTAssertEqual(result.posts, 1)
            XCTAssertEqual(result.effects, 0); XCTAssertEqual(result.forbidden_writes, 0)
            capture("provider-failed-" + language)
            return
        }
        let partial = app.staticTexts["run.stream.text"]
        let received = partial.waitForExistence(timeout: 25)
        if !received {
            capture("missing-stream-" + language)
            print("RUN_UI_STATUS", app.staticTexts["run.display.status"].exists ? app.staticTexts["run.display.status"].label : "no status")
        }
        XCTAssertTrue(received)
        XCTAssertFalse(partial.label.isEmpty)
        let prefix = partial.label
        let before = try await proof(fixture)
        XCTAssertEqual(before.status, "running"); XCTAssertTrue(before.text.hasPrefix(prefix))
        capture("stream-partial-" + language)
        if mode == "stop" {
            tap("run.stop")
            status(language == "en" ? "Cancelled" : "已取消")
            XCTAssertEqual(app.staticTexts["run.display.text"].label, prefix)
            _ = try await call("/release", ["case": fixture.conversation])
        } else {
            _ = try await call("/release", ["case": fixture.conversation])
            status(language == "en" ? "Completed" : "已完成")
        }
        let saved = try await proof(fixture)
        XCTAssertEqual(saved.status, mode == "stop" ? "cancelled" : "completed")
        XCTAssertEqual(app.staticTexts["run.display.text"].label, saved.text)
        XCTAssertEqual(saved.posts, 1); XCTAssertEqual(saved.receipts, 1); XCTAssertEqual(saved.provider_calls, 1)
        XCTAssertEqual(saved.cancellations, mode == "stop" ? 1 : 0)
        XCTAssertEqual(saved.effects, 0); XCTAssertEqual(saved.forbidden_writes, 0)
        capture(mode + "-persisted-" + language)
        try launch(fixture, language: language, restore: true)
        tap("assistant.history")
        tap("recovery.action." + (try XCTUnwrap(saved.message_id)))
        tap("assistant.panel.done")
        status(language == "en" ? (mode == "stop" ? "Cancelled" : "Completed") : (mode == "stop" ? "已取消" : "已完成"))
        XCTAssertEqual(app.staticTexts["run.display.text"].label, saved.text)
        let reopened = try await proof(fixture)
        XCTAssertEqual(reopened.provider_calls, 1); XCTAssertEqual(reopened.posts, 1)
        XCTAssertEqual(reopened.cancellations, saved.cancellations)
        capture(mode + "-read-after-reopen-" + language)
    }
    func testStreamEnglish() async throws { try await run("normal", language: "en") }
    func testStreamChinese() async throws { try await run("normal", language: "zh-Hans") }
    func testStopEnglish() async throws { try await run("stop", language: "en") }
    func testStopChinese() async throws { try await run("stop", language: "zh-Hans") }
    func testFailureEnglish() async throws { try await run("failure", language: "en") }
    func testFailureChinese() async throws { try await run("failure", language: "zh-Hans") }
    func testReleaseClosed() async throws {
        continueAfterFailure = false
        let fixture = try JSONDecoder().decode(Fixture.self, from: await call("/prepare", ["mode": "release", "language": "en"]))
        app = XCUIApplication(bundleIdentifier: bundle)
        defer { app.terminate() }
        app.launchEnvironment = ["G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": fixture.endpoint,
            "G2C_DEV_ACCOUNTS": String(data: try JSONEncoder().encode(fixture.accounts), encoding: .utf8)!]
        app.launch(); XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["run.stop"].exists)
        XCTAssertFalse(app.buttons["assistant.send"].exists)
        let result = try await proof(fixture)
        XCTAssertEqual(result.posts, 0); XCTAssertEqual(result.cancellations, 0); XCTAssertEqual(result.provider_calls, 0)
        capture("release-run-closed")
    }
}
