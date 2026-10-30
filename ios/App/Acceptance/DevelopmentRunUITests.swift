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
        let runtime_role: String
        let pending_deliveries: Int
        let ledger_fingerprint: String
        let original_fingerprint: String
        let registered_fingerprint: String?
        let registered_operations: Int
        let exposure: Int
        let ledger_attempts: Int
        let usage_receipts: Int
        let tool_steps: Int
        let budget_stage: String
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
    private func proof(_ fixture: Fixture, settled: Bool = false) async throws -> Proof {
        try JSONDecoder().decode(Proof.self, from: await call("/proof", ["case": fixture.conversation, "settled": settled ? "1" : "0"]))
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
    private func launch(_ fixture: Fixture, language: String, restore: Bool = false, account: String? = nil) throws {
        let choice = account ?? fixture.choice
        app?.terminate(); app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": fixture.endpoint,
            "G2C_DEV_TOKEN": "", "G2C_DEV_ACCOUNTS": restore ? "{}" : String(data: try JSONEncoder().encode(fixture.accounts), encoding: .utf8)!]
        app.launch(); XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        tap(language == "en" ? "Memory" : "记忆"); tap("memory.account")
        if restore { tap("account.development.restore") }
        else { tap("account.development.signout"); tap("account.development.signin." + choice) }
        let signed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", fixture.subjects[choice]!), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [signed], timeout: 20), .completed)
        tap(language == "en" ? "Assistant" : "助手")
    }
    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }
    private func run(_ mode: String, language: String, fence: String? = nil) async throws {
        continueAfterFailure = false
        defer { app?.terminate() }
        let fixture = try JSONDecoder().decode(Fixture.self, from: await call("/prepare", ["mode": mode, "language": language]))
        try launch(fixture, language: language)
        tap("assistant.serverHistory"); tap("history.loadConversations")
        tap("history.conversation." + fixture.conversation); tap("assistant.panel.done")
        let draft = mode.hasPrefix("draft_")
        let stopping = mode == "stop" || mode == "draft_stop"
        if draft {
            let intent = app.switches["assistant.intent"]
            XCTAssertTrue(intent.waitForExistence(timeout: 8))
            intent.switches.firstMatch.tap()
            XCTAssertEqual(intent.value as? String, "1")
        }
        send(fixture.prompt)
        if mode != "failure" && mode != "unknown" {
            let partial = app.staticTexts["run.stream.text"]
            XCTAssertTrue(partial.waitForExistence(timeout: 25))
            let prefix = partial.label
            XCTAssertFalse(prefix.isEmpty)
            let before = try await proof(fixture)
            XCTAssertEqual(before.status, "running"); XCTAssertTrue(before.text.hasPrefix(prefix))
            XCTAssertEqual(before.tool_steps, 0)
            capture("stream-partial-" + language)
            if stopping {
                tap("run.stop")
                status(language == "en" ? "Cancelled" : "已取消")
                XCTAssertEqual(app.staticTexts["run.display.text"].label, prefix)
            }
            _ = try await call("/release", ["case": fixture.conversation])
            if !stopping { try await terminal(fixture, expected: "completed", language: language) }
        }
        if mode == "budget_answer" {
            let first = try await proof(fixture, settled: true)
            XCTAssertEqual(first.exposure, 1); XCTAssertEqual(first.provider_calls, 1)
            XCTAssertEqual(first.receipts, 1); XCTAssertEqual(first.status, "completed")
            waitCard(language == "en" ? "No draft was requested for this message" : "此消息未请求草稿")
            capture("answer-budget-first-call-" + language)
            send(fixture.prompt + " second")
        }
        let expectedStatus = stopping ? "cancelled" : mode == "unknown" ? "unknown" : ["failure", "budget_answer"].contains(mode) ? "failed" : "completed"
        try await terminal(fixture, expected: expectedStatus, language: language)
        let saved = try await proof(fixture, settled: true)
        try check(mode, language: language, result: saved, expectedStatus: expectedStatus)
        capture(mode + "-persisted-" + language)
        try checkOriginal(fixture.prompt + (mode == "budget_answer" ? " second" : ""), selection: mode == "draft_published", language: language)
        _ = try await call("/reconcile", ["case": fixture.conversation])
        try launch(fixture, language: language, restore: true)
        tap("assistant.history"); tap("recovery.action." + (try XCTUnwrap(saved.message_id))); tap("assistant.panel.done")
        try await terminal(fixture, expected: expectedStatus, language: language)
        let reopened = try await proof(fixture, settled: true)
        try check(mode, language: language, result: reopened, expectedStatus: expectedStatus)
        XCTAssertEqual(reopened.message_id, saved.message_id)
        XCTAssertEqual(reopened.text, saved.text)
        XCTAssertEqual(reopened.provider_calls, saved.provider_calls)
        XCTAssertEqual(reopened.posts, saved.posts)
        XCTAssertEqual(reopened.cancellations, saved.cancellations)
        XCTAssertEqual(reopened.ledger_fingerprint, saved.ledger_fingerprint)
        XCTAssertEqual(reopened.original_fingerprint, saved.original_fingerprint)
        XCTAssertEqual(reopened.registered_fingerprint, saved.registered_fingerprint)
        XCTAssertEqual(reopened.exposure, saved.exposure)
        XCTAssertEqual(reopened.usage_receipts, saved.usage_receipts)
        XCTAssertGreaterThanOrEqual(reopened.draft_reads, 2)
        capture(mode + "-read-after-reopen-" + language)
        try checkOriginal(fixture.prompt + (mode == "budget_answer" ? " second" : ""), selection: false, language: language)
        if mode == "draft_published" {
            let other = fixture.choice == "A" ? "B" : "A"
            try launch(fixture, language: language, account: other)
            XCTAssertFalse(app.staticTexts["run.display.text"].exists)
            XCTAssertFalse(app.textViews["assistant.originalText"].exists)
            tap("assistant.serverHistory"); tap("history.loadConversations")
            XCTAssertTrue(app.staticTexts[language == "en" ? "The read returned no records." : "本次读取未返回记录。"].firstMatch.waitForExistence(timeout: 15))
            XCTAssertFalse(app.buttons["history.conversation." + fixture.conversation].exists)
            capture("foreign-account-empty-history-" + language)
            _ = try await call("/observe-foreign-ui", ["case": fixture.conversation])
        }
        if let fence { try await originalFence(fixture, saved: reopened, kind: fence) }
    }

    private func originalFence(_ fixture: Fixture, saved: Proof, kind: String) async throws {
        XCTAssertNotNil(saved.registered_fingerprint)
        XCTAssertGreaterThan(saved.registered_operations, 0)
        if kind == "switch" {
            // The earlier no-injected-token reopen remains checked. This phase
            // loads the explicit account choices before holding the old read.
            try launch(fixture, language: "en")
            tap("assistant.history"); tap("recovery.action." + (try XCTUnwrap(saved.message_id))); tap("assistant.panel.done")
            try await terminal(fixture, expected: "failed", language: "en")
        }
        if kind == "expired" {
            let short = try JSONDecoder().decode(Fixture.self, from: await call("/renew-short-token", ["case": fixture.conversation]))
            try launch(short, language: "en")
            tap("assistant.history"); tap("recovery.action." + (try XCTUnwrap(saved.message_id))); tap("assistant.panel.done")
            try await terminal(short, expected: "failed", language: "en")
            XCUIDevice.shared.press(.home)
            _ = try await call("/wait-real-expiry", ["case": fixture.conversation])
            app.activate()
        } else {
            _ = try await call("/hold-original-read", ["case": fixture.conversation])
            tap("run.snapshot.read")
            _ = try await call("/wait-original-held", ["case": fixture.conversation])
            if kind == "revoked" {
                _ = try await call("/withdraw-access", ["case": fixture.conversation])
                XCUIDevice.shared.press(.home); app.activate()
            }
        }
        tap("Memory")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
        if kind == "switch" {
            tap("account.development.signin.B")
            let signed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", fixture.subjects["B"]!), object: app.staticTexts["account.development.status"])
            XCTAssertEqual(XCTWaiter.wait(for: [signed], timeout: 15), .completed)
        } else {
            let rejected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", "Sign-in was rejected"), object: app.staticTexts["account.development.status"])
            XCTAssertEqual(XCTWaiter.wait(for: [rejected], timeout: 15), .completed)
        }
        if kind != "expired" { _ = try await call("/release-original-read", ["case": fixture.conversation]) }
        tap("Assistant")
        XCTAssertFalse(app.staticTexts["run.budget.status"].exists)
        XCTAssertFalse(app.staticTexts["run.display.text"].exists)
        XCTAssertFalse(app.textViews["assistant.originalText"].exists)
        capture("registered-original-" + kind)
        let after = try await proof(fixture, settled: true)
        XCTAssertEqual(after.provider_calls, saved.provider_calls); XCTAssertEqual(after.posts, saved.posts)
        XCTAssertEqual(after.original_fingerprint, saved.original_fingerprint)
        XCTAssertEqual(after.ledger_fingerprint, saved.ledger_fingerprint)
        XCTAssertEqual(after.registered_fingerprint, saved.registered_fingerprint)
        let restored = try JSONDecoder().decode(Fixture.self, from: await call("/restore-identity", ["case": fixture.conversation]))
        try launch(restored, language: "en")
        tap("assistant.history"); tap("recovery.action." + (try XCTUnwrap(saved.message_id))); tap("assistant.panel.done")
        try await terminal(restored, expected: "failed", language: "en")
        let recovered = try await proof(fixture, settled: true)
        XCTAssertEqual(recovered.message_id, saved.message_id)
        XCTAssertEqual(recovered.original_fingerprint, saved.original_fingerprint)
        XCTAssertEqual(recovered.registered_fingerprint, saved.registered_fingerprint)
        XCTAssertEqual(recovered.ledger_fingerprint, saved.ledger_fingerprint)
        XCTAssertEqual(recovered.provider_calls, saved.provider_calls); XCTAssertEqual(recovered.posts, saved.posts)
        try check("budget_answer", language: "en", result: recovered, expectedStatus: "failed")
    }
    /// One explicit user read after an observed producer refusal. Never retry a write/model.
    private func terminal(_ fixture: Fixture, expected: String, language: String) async throws {
        let value = app.staticTexts["run.display.status"]
        let unavailable = language == "en" ? "Original run unavailable; result unknown" : "原运行不可用，结果未知"
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format:"label BEGINSWITH %@ OR label == %@", statusLabel(expected, language), unavailable), object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[ready], timeout:30), .completed)
        if value.label == unavailable {
            XCTAssertFalse(app.staticTexts["run.display.text"].exists)
            XCTAssertFalse(app.staticTexts["run.stream.text"].exists)
            let card = app.descendants(matching:.any).matching(identifier:"run.draft.status").firstMatch
            XCTAssertFalse(card.label.contains("Budget exhausted")); XCTAssertFalse(card.label.contains("预算已耗尽"))
            capture("producer-read-unavailable-" + language)
            let before = try await proof(fixture, settled:true)
            _ = try await call("/observe-read-recovery", ["case":fixture.conversation])
            tap("run.snapshot.read")
            status(statusLabel(expected, language))
            let after = try await proof(fixture, settled:true)
            XCTAssertEqual(after.provider_calls, before.provider_calls)
            XCTAssertEqual(after.posts, before.posts)
            XCTAssertEqual(after.ledger_fingerprint, before.ledger_fingerprint)
        } else { status(statusLabel(expected, language)) }
    }
    private func checkOriginal(_ expected: String, selection: Bool, language: String) throws {
        let original = app.textViews["assistant.originalText"]
        XCTAssertTrue(original.exists)
        let value = try XCTUnwrap(original.value as? String)
        XCTAssertEqual(Array(value.utf8), Array(expected.utf8))
        if selection {
            let scroll = app.scrollViews.firstMatch
            for _ in 0..<8 { if scroll.frame.contains(original.frame) && original.isHittable { break }; scroll.swipeUp() }
            XCTAssertTrue(original.isHittable)
            original.press(forDuration: 1)
            let names = NSPredicate(format:"label IN %@", ["Copy", "拷贝", "复制"])
            let menu = app.menuItems.matching(names).firstMatch
            let copy = menu.waitForExistence(timeout: 2) ? menu : app.buttons.matching(names).firstMatch
            XCTAssertTrue(copy.waitForExistence(timeout: 5)); XCTAssertTrue(copy.isEnabled)
            capture("original-selection-menu-" + language)
        }
    }
    private func send(_ text: String) {
        let field = app.textViews["assistant.draft"]
        XCTAssertTrue(field.waitForExistence(timeout: 10)); field.tap(); field.typeText(text)
        XCTAssertEqual(field.value as? String, text)
        if app.buttons["Done"].exists { tap("Done") } else if app.buttons["完成"].exists { tap("完成") }
        tap("assistant.send")
    }
    private func statusLabel(_ status: String, _ language: String) -> String {
        switch status {
        case "failed": language == "en" ? "Failed" : "运行失败"
        case "unknown": language == "en" ? "Result unknown" : "结果未知"
        case "cancelled": language == "en" ? "Cancelled" : "已取消"
        default: language == "en" ? "Completed" : "已完成"
        }
    }
    private func waitCard(_ text: String) {
        let value = app.descendants(matching: .any).matching(identifier: "run.draft.status").firstMatch
        XCTAssertTrue(value.waitForExistence(timeout: 10))
        let match = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", text), object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[match], timeout:15), .completed)
    }
    private func check(_ mode: String, language: String, result: Proof, expectedStatus: String) throws {
        let draft = mode.hasPrefix("draft_")
        let stopping = mode == "stop" || mode == "draft_stop"
        let published = mode == "draft_published"
        let stage = mode == "budget_answer" ? "answer" : mode == "draft_budget" ? "draft" : "none"
        let expected: String
        let outcome: String?
        switch mode {
        case "draft_budget": expected = language == "en" ? "Draft generation budget exhausted" : "草稿生成预算已耗尽"; outcome = "budget_exhausted"
        case "draft_published": expected = language == "en" ? "Draft candidate recorded; not a saved trip" : "已记录草稿候选，尚非正式行程"; outcome = nil
        case "draft_validation": expected = language == "en" ? "Draft failed validation; no candidate published" : "草稿校验失败，未发布候选"; outcome = "validation_failed"
        case "draft_provider": expected = language == "en" ? "Draft generation failed; no candidate published" : "草稿生成失败，未发布候选"; outcome = "provider_failed"
        case "draft_unknown": expected = language == "en" ? "Draft generation result unknown; do not generate again" : "草稿生成结果未知，请勿再次生成"; outcome = "provider_unknown"
        case "draft_stop": expected = language == "en" ? "No draft result recorded; outcome unknown" : "尚无草稿结果记录，结果未知"; outcome = nil
        default: expected = language == "en" ? "No draft was requested for this message" : "此消息未请求草稿"; outcome = nil
        }
        waitCard(expected)
        let value = app.descendants(matching: .any).matching(identifier: "run.draft.status").firstMatch
        let label = value.label
        XCTAssertFalse(label.contains("PRIVATE_SENTINEL"))
        XCTAssertTrue(label.contains(language == "en" ? "Draft result" : "草稿结果"))
        let runLabel = expectedStatus == "failed" ? (language == "en" ? "Failed" : "失败") : expectedStatus == "unknown" ? (language == "en" ? "Unknown" : "未知") : expectedStatus == "cancelled" ? (language == "en" ? "Cancelled" : "已取消") : (language == "en" ? "Completed" : "已完成")
        XCTAssertTrue(label.contains((language == "en" ? "Run state at draft read: " : "读取草稿时的运行状态：") + runLabel))
        if stage == "none" {
            XCTAssertFalse(label.contains("Budget exhausted")); XCTAssertFalse(label.contains("预算已耗尽"))
        } else {
            let budget = language == "en" ? "Budget exhausted before \(stage) generation" : stage == "answer" ? "生成回答前预算已耗尽" : "生成草稿前预算已耗尽"
            XCTAssertTrue(label.contains(budget))
        }
        XCTAssertEqual(result.runtime_role, "cj_m1_runtime")
        XCTAssertEqual(result.pending_deliveries, 0)
        XCTAssertEqual(result.status, expectedStatus)
        XCTAssertFalse(app.buttons["run.stop"].isEnabled)
        XCTAssertFalse(app.buttons["assistant.queryOriginal"].isEnabled)
        XCTAssertEqual(result.budget_stage, stage)
        XCTAssertEqual(result.posts, mode == "budget_answer" ? 2 : 1)
        XCTAssertEqual(result.receipts, mode == "budget_answer" ? 2 : 1)
        XCTAssertEqual(result.provider_calls, draft && !stopping && mode != "draft_budget" ? 2 : 1)
        XCTAssertEqual(result.draft_calls, draft && !stopping && mode != "draft_budget" ? 1 : 0)
        XCTAssertEqual(result.exposure, draft && !stopping && mode != "draft_budget" ? 2 : 1)
        XCTAssertEqual(result.cancellations, stopping ? 1 : 0)
        XCTAssertEqual(result.effects, published ? 1 : 0)
        XCTAssertEqual(result.published_effects, published ? 1 : 0)
        XCTAssertEqual(result.pending_proposals, published ? 1 : 0)
        XCTAssertEqual(result.formal_trips, 0); XCTAssertTrue(result.proposal_binding_valid)
        XCTAssertEqual(result.draft_outcome, outcome)
        XCTAssertEqual(result.creation_intent, draft ? "consider_trip" : "none")
        XCTAssertEqual(result.forbidden_writes, 0); XCTAssertEqual(result.tool_steps, 0)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format:"label CONTAINS[c] 'tool executed' OR label CONTAINS '工具已执行' OR label CONTAINS '已执行工具'")).firstMatch.exists)
        if ["failed", "unknown"].contains(expectedStatus) {
            XCTAssertEqual(result.text, "")
            XCTAssertFalse(app.staticTexts["run.display.text"].exists)
            XCTAssertFalse(app.staticTexts["run.stream.text"].exists)
        } else { XCTAssertEqual(app.staticTexts["run.display.text"].label, result.text) }
        let scroll = app.scrollViews.firstMatch
        for _ in 0..<8 {
            if scroll.frame.contains(value.frame) && value.isHittable { break }
            if value.frame.maxY > scroll.frame.maxY { scroll.swipeUp() } else { scroll.swipeDown() }
        }
        XCTAssertTrue(scroll.frame.contains(value.frame))
        XCTAssertTrue(value.isHittable)
        try audit("RUN_AX " + language)
    }
    private func audit(_ context: String) throws {
        var issues = 0
        continueAfterFailure = true
        defer { continueAfterFailure = false }
        try app.performAccessibilityAudit(for: .all) { issue in
            issues += 1
            print(context, issue.detailedDescription, issue.element?.label ?? "unavailable", issue.element?.frame ?? .zero)
            return false // Every issue is still an XCTest failure; never filtered.
        }
        continueAfterFailure = false
        XCTAssertEqual(issues, 0) // Stop before further UI work if any audit check failed.
    }
    func testAnswerBudgetEnglish() async throws { try await run("budget_answer", language:"en") }
    func testAnswerBudgetChinese() async throws { try await run("budget_answer", language:"zh-Hans") }
    func testDraftBudgetEnglish() async throws { try await run("draft_budget", language:"en") }
    func testDraftBudgetChinese() async throws { try await run("draft_budget", language:"zh-Hans") }
    func testUnknownEnglish() async throws { try await run("unknown", language:"en") }
    func testUnknownChinese() async throws { try await run("unknown", language:"zh-Hans") }
    func testRegisteredSwitchOriginal() async throws { try await run("budget_answer", language:"en", fence:"switch") }
    func testRegisteredRevokedOriginal() async throws { try await run("budget_answer", language:"en", fence:"revoked") }
    func testRegisteredExpiredOriginal() async throws { try await run("budget_answer", language:"en", fence:"expired") }
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
        XCTAssertEqual(result.exposure, 0); XCTAssertEqual(result.ledger_attempts, 0)
        try audit("RELEASE_AX")
        capture("release-run-closed")
    }
}
