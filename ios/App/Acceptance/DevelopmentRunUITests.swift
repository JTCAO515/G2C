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
        let requests: Int
        let status: String?
        let text: String
        let effects: Int
        let message_id: String?
        let receipts: Int
        let provider_calls: Int
        let posts: Int
        let cancellations: Int
        let draft_outcome: String?
        let draft_calls: Int
        let published_effects: Int
        let pending_proposals: Int
        let formal_trips: Int
        let proposal_binding_valid: Bool
        let creation_intent: String?
        let draft_reads: Int
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
        let draft = mode.hasPrefix("draft_")
        let stopping = mode == "stop" || mode == "draft_stop"
        if draft {
            let intent = app.switches["assistant.intent"]
            XCTAssertTrue(intent.waitForExistence(timeout: 8))
            intent.switches.firstMatch.tap()
            XCTAssertEqual(intent.value as? String, "1")
        }
        tap("assistant.send")
        if mode == "failure" {
            status(language == "en" ? "Failed" : "运行失败")
            XCTAssertFalse(app.staticTexts["run.display.text"].exists)
            XCTAssertFalse(app.staticTexts["run.stream.text"].exists)
            let result = try await proof(fixture)
            XCTAssertEqual(result.status, "failed"); XCTAssertEqual(result.text, "")
            XCTAssertEqual(result.provider_calls, 1); XCTAssertEqual(result.posts, 1)
            XCTAssertEqual(result.receipts, 1); XCTAssertEqual(result.cancellations, 0)
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
        if stopping {
            tap("run.stop")
            status(language == "en" ? "Cancelled" : "已取消")
            XCTAssertEqual(app.staticTexts["run.display.text"].label, prefix)
            _ = try await call("/release", ["case": fixture.conversation])
        } else {
            _ = try await call("/release", ["case": fixture.conversation])
            status(language == "en" ? "Completed" : "已完成")
        }
        let saved = try await proof(fixture)
        XCTAssertEqual(saved.status, stopping ? "cancelled" : "completed")
        XCTAssertEqual(app.staticTexts["run.display.text"].label, saved.text)
        XCTAssertEqual(saved.posts, 1); XCTAssertEqual(saved.receipts, 1); XCTAssertEqual(saved.provider_calls, draft && !stopping ? 2 : 1)
        XCTAssertEqual(saved.cancellations, stopping ? 1 : 0)
        XCTAssertEqual(saved.effects, mode == "draft_published" ? 1 : 0); XCTAssertEqual(saved.forbidden_writes, 0)
        if draft { try checkDraft(mode, language: language, proof: saved) }
        capture(mode + "-persisted-" + language)
        try launch(fixture, language: language, restore: true)
        tap("assistant.history")
        tap("recovery.action." + (try XCTUnwrap(saved.message_id)))
        tap("assistant.panel.done")
        status(language == "en" ? (stopping ? "Cancelled" : "Completed") : (stopping ? "已取消" : "已完成"))
        XCTAssertEqual(app.staticTexts["run.display.text"].label, saved.text)
        let reopened = try await proof(fixture)
        XCTAssertEqual(reopened.provider_calls, saved.provider_calls); XCTAssertEqual(reopened.posts, 1)
        XCTAssertEqual(reopened.cancellations, saved.cancellations)
        if draft { try checkDraft(mode, language: language, proof: reopened) }
        capture(mode + "-read-after-reopen-" + language)
    }
    private func checkDraft(_ mode: String, language: String, proof: Proof) throws {
        let expected: String
        let outcome: String?
        switch mode {
        case "draft_published": expected = language == "en" ? "Draft candidate recorded; not a saved trip" : "已记录草稿候选，尚非正式行程"; outcome = nil
        case "draft_validation": expected = language == "en" ? "Draft failed validation; no candidate published" : "草稿校验失败，未发布候选"; outcome = "validation_failed"
        case "draft_provider": expected = language == "en" ? "Draft generation failed; no candidate published" : "草稿生成失败，未发布候选"; outcome = "provider_failed"
        case "draft_unknown": expected = language == "en" ? "Draft generation result unknown; do not generate again" : "草稿生成结果未知，请勿再次生成"; outcome = "provider_unknown"
        default: expected = language == "en" ? "No draft result recorded; outcome unknown" : "尚无草稿结果记录，结果未知"; outcome = nil
        }
        let value = app.descendants(matching: .any).matching(identifier: "run.draft.status").firstMatch
        XCTAssertTrue(value.waitForExistence(timeout: 10))
        let match = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", expected), object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[match], timeout:15), .completed)
        XCTAssertTrue(value.label.contains(language == "en" ? "Draft result" : "草稿结果"))
        XCTAssertTrue(value.label.contains(language == "en" ? "Run state at draft read:" : "读取草稿时的运行状态："))
        XCTAssertTrue(value.label.contains(language == "en" ? (mode == "draft_stop" ? "Cancelled" : "Completed") : (mode == "draft_stop" ? "已取消" : "已完成")))
        let visible = NSPredicate(format:"exists == true AND hittable == true")
        for _ in 0..<10 { if visible.evaluate(with:value) { break }; app.swipeUp() }
        XCTAssertTrue(visible.evaluate(with:value))
        print("DRAFT_FRAME_BEFORE", value.frame)
        for _ in 0..<5 {
            if value.frame.maxY < app.frame.height * 0.60 { break }
            app.scrollViews.firstMatch.swipeUp()
        }
        print("DRAFT_FRAME_AFTER", value.frame)
        XCTAssertTrue(visible.evaluate(with:value))
        try app.performAccessibilityAudit(for: [.sufficientElementDescription, .textClipped]) { issue in
            print("DRAFT_AX \(language): \(issue.compactDescription); \(issue.element?.label ?? "unavailable")")
            return false
        }
        XCTAssertEqual(proof.creation_intent, "consider_trip")
        XCTAssertGreaterThanOrEqual(proof.draft_reads, 1)
        XCTAssertEqual(proof.published_effects, mode == "draft_published" ? 1 : 0)
        XCTAssertEqual(proof.pending_proposals, mode == "draft_published" ? 1 : 0)
        XCTAssertEqual(proof.formal_trips, 0)
        XCTAssertTrue(proof.proposal_binding_valid)
        XCTAssertEqual(proof.draft_outcome, outcome)
        XCTAssertEqual(proof.draft_calls, mode == "draft_stop" ? 0 : 1)
        XCTAssertFalse(value.label.contains("PRIVATE_SENTINEL"))
    }
    func testDraftPublishedEnglish() async throws { try await run("draft_published", language:"en") }
    func testDraftPublishedChinese() async throws { try await run("draft_published", language:"zh-Hans") }
    func testDraftValidationEnglish() async throws { try await run("draft_validation", language:"en") }
    func testDraftValidationChinese() async throws { try await run("draft_validation", language:"zh-Hans") }
    func testDraftProviderEnglish() async throws { try await run("draft_provider", language:"en") }
    func testDraftProviderChinese() async throws { try await run("draft_provider", language:"zh-Hans") }
    func testDraftUnknownEnglish() async throws { try await run("draft_unknown", language:"en") }
    func testDraftUnknownChinese() async throws { try await run("draft_unknown", language:"zh-Hans") }
    func testDraftStopEnglish() async throws { try await run("draft_stop", language:"en") }
    func testDraftStopChinese() async throws { try await run("draft_stop", language:"zh-Hans") }
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
        XCTAssertEqual(result.requests, 0)
        capture("release-run-closed")
    }
}
