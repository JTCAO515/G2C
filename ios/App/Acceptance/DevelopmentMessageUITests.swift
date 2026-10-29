import XCTest
import Foundation

@MainActor final class DevelopmentMessageUITests: XCTestCase {
    private let bundle = "space.go2china.messages.acceptance"
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private struct Fixture: Decodable {
        let endpoint: String
        let accounts: [String: String]
        let subjects: [String: String]
        let primary: [String: String]
        let before: [String: String]
        let after: [String: String]
        let last: [String: String]
    }
    private struct Proof: Decodable {
        let posts: Int
        let receipts: Int
        let conversations: Int
        let message_id: String?
        let creation_intent: String?
        let trip_is_null: Bool
        let matching_originals: Bool
        let status_reads: Int
        let forbidden_writes: Int
    }
    private func call(_ path: String) async throws -> Data {
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(URL(string: control + path)))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return data
    }
    private func proof(_ account: String, _ conversation: String) async throws -> Proof {
        var url = URLComponents(string: control + "/proof")!
        url.queryItems = [URLQueryItem(name: "account", value: account), URLQueryItem(name: "conversation", value: conversation)]
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return try JSONDecoder().decode(Proof.self, from: data)
    }
    private func tap(_ id: String, towardTop: Bool = false) {
        let button = app.buttons.matching(identifier: id).firstMatch
        _ = button.waitForExistence(timeout: 2)
        let visible = NSPredicate(format: "exists == true AND hittable == true")
        for _ in 0..<14 {
            if visible.evaluate(with: button) { break }
            if towardTop { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(visible.evaluate(with: button), id)
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 15), .completed, id)
        button.tap()
    }
    private func status(_ fragment: String) {
        let node = app.staticTexts["assistant.recoveryStatus"]
        XCTAssertTrue(node.waitForExistence(timeout: 8))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", fragment), object: node)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 20), .completed, node.label)
    }
    private func account(_ language: String) {
        tap(language == "en" ? "Memory" : "记忆")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
    }
    private func launch(_ fixture: Fixture, _ language: String, restore: Bool = false, choice: String = "A") throws {
        continueAfterFailure = false
        app?.terminate(); app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": fixture.endpoint,
                                 "G2C_DEV_TOKEN": "", "G2C_DEV_ACCOUNTS": "{}"]
        if !restore { app.launchEnvironment["G2C_DEV_ACCOUNTS"] = String(data: try JSONEncoder().encode(fixture.accounts), encoding: .utf8) }
        app.launch(); XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        account(language)
        if restore { tap("account.development.restore") }
        else { tap("account.development.signout"); tap("account.development.signin." + choice) }
        let subject = try XCTUnwrap(fixture.subjects[choice])
        let expected = language == "en" ? "Signed in as " + subject : "已登录：" + subject
        let signed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", expected), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [signed], timeout: 20), .completed)
        tap(language == "en" ? "Assistant" : "助手")
    }
    private func select(_ cid: String, fixture: Fixture, choice: String, language: String, paginate: Bool = false) {
        tap("assistant.serverHistory")
        tap("history.loadConversations")
        XCTAssertTrue(app.buttons["history.conversation." + fixture.primary[choice]!].waitForExistence(timeout: 15))
        if paginate {
            tap("history.nextConversations")
            XCTAssertTrue(app.buttons["history.conversation." + fixture.last[choice]!].waitForExistence(timeout: 15))
            capture(language + "-conversation-page-two")
        }
        tap("history.conversation." + cid, towardTop: paginate)
        tap("assistant.panel.done")
        XCTAssertTrue(app.staticTexts["assistant.conversation"].waitForExistence(timeout: 10))
    }
    private var field: XCUIElement { app.textViews["assistant.draft"] }
    private func enter(_ text: String) {
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: field)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 15), .completed)
        field.tap()
        if let old = field.value as? String, old != "Start chatting", old != "开始聊天", !old.isEmpty {
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count))
        }
        field.typeText(text)
        XCTAssertEqual(field.value as? String, text)
        if app.buttons["Done"].exists { tap("Done") }
        else if app.buttons["完成"].exists { tap("完成") }
    }
    private func language(from old: String, to next: String) {
        tap(old == "en" ? "Memory" : "记忆")
        if app.staticTexts["account.development.status"].exists { app.navigationBars.buttons.firstMatch.tap() }
        if !app.buttons["English"].exists { tap("memory.language") }
        tap(next == "en" ? "English" : "简体中文")
        tap(next == "en" ? "Assistant" : "助手")
    }
    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }
    private func normal(_ language: String, _ choice: String) async throws {
        _ = try await call("/normal")
        let fixture = try JSONDecoder().decode(Fixture.self, from: await call("/config"))
        try launch(fixture, language, choice: choice)
        let cid = try XCTUnwrap(fixture.primary[choice])
        select(cid, fixture: fixture, choice: choice, language: language, paginate: true)
        status(language == "en" ? "Ready" : "可以编辑")
        let text = "CJ164 " + choice + " 北京三日 / three days"
        enter(text)
        let intent = app.switches["assistant.intent"]
        XCTAssertTrue(intent.waitForExistence(timeout: 8))
        let control = intent.switches.firstMatch
        XCTAssertTrue(control.exists && control.isHittable)
        control.tap()
        capture("intent-after-tap-" + language)
        XCTAssertEqual(intent.value as? String, "1", "Trip planning must be selected before changing language")
        let other = language == "en" ? "zh-Hans" : "en"
        self.language(from: language, to: other)
        XCTAssertEqual(field.value as? String, text)
        self.language(from: other, to: language)
        XCTAssertEqual(field.value as? String, text)
        XCTAssertEqual(intent.value as? String, "1", "Language changes must preserve trip planning")
        tap("assistant.send")
        status(language == "en" ? "confirmed receipt" : "确认回执")
        let saved = try await proof(choice, cid)
        XCTAssertEqual(saved.posts, 1); XCTAssertEqual(saved.receipts, 1); XCTAssertEqual(saved.conversations, 23)
        XCTAssertEqual(saved.creation_intent, "consider_trip"); XCTAssertTrue(saved.trip_is_null)
        XCTAssertTrue(saved.matching_originals); XCTAssertEqual(saved.forbidden_writes, 0)
        let mid = try XCTUnwrap(saved.message_id)
        tap("assistant.serverHistory"); tap("history.loadMessages")
        XCTAssertTrue(app.staticTexts["history.message.seed-" + choice + "-00"].waitForExistence(timeout: 15))
        tap("history.nextMessages")
        XCTAssertTrue(app.staticTexts["history.message." + mid].waitForExistence(timeout: 15))
        capture(language + "-actual-message-page-two")
        tap("assistant.panel.done")
        let draft = "CJ164 unsent " + choice + " 未发送草稿"
        enter(draft)
        try launch(fixture, language, restore: true, choice: choice)
        select(cid, fixture: fixture, choice: choice, language: language, paginate: true)
        status(language == "en" ? "Ready" : "可以编辑")
        XCTAssertEqual(field.value as? String, draft)
        tap("assistant.serverHistory"); tap("history.loadMessages")
        XCTAssertTrue(app.staticTexts["history.message.seed-" + choice + "-00"].waitForExistence(timeout: 15))
        tap("history.nextMessages")
        let originalMessage = app.staticTexts["history.message." + mid]
        XCTAssertTrue(originalMessage.waitForExistence(timeout: 15))
        XCTAssertTrue(originalMessage.label.contains(text))
        capture(language + "-original-message-pages-after-reopen")
        tap("assistant.panel.done")
        XCTAssertEqual(field.value as? String, draft)
        let reopenedProof = try await proof(choice, cid)
        XCTAssertEqual(reopenedProof.posts, 1)
        capture(language + "-encrypted-draft-after-reopen")
        app.terminate()
    }
    func testNormalEnglish() async throws { try await normal("en", "A") }
    func testNormalChinese() async throws { try await normal("zh-Hans", "B") }

    private func unknown(_ language: String, _ choice: String, afterCommit: Bool) async throws {
        _ = try await call("/normal")
        let fixture = try JSONDecoder().decode(Fixture.self, from: await call("/config"))
        try launch(fixture, language, choice: choice)
        let cid = try XCTUnwrap((afterCommit ? fixture.after : fixture.before)[choice])
        select(cid, fixture: fixture, choice: choice, language: language)
        status(language == "en" ? "Ready" : "可以编辑")
        enter("CJ164 original " + choice + (afterCommit ? " after" : " before"))
        _ = try await call(afterCommit ? "/after" : "/before")
        tap("assistant.send")
        status(language == "en" ? "unknown" : "结果未知")
        XCTAssertFalse(app.buttons["assistant.send"].isEnabled)
        let first = try await proof(choice, cid)
        XCTAssertEqual(first.posts, 1); XCTAssertEqual(first.receipts, afterCommit ? 1 : 0)
        try launch(fixture, language, restore: true, choice: choice)
        select(cid, fixture: fixture, choice: choice, language: language)
        status(language == "en" ? "needs checking" : "待核对")
        XCTAssertFalse(app.buttons["assistant.resubmit"].exists)
        let beforeQuery = try await proof(choice, cid)
        XCTAssertEqual(beforeQuery.posts, 1)
        tap("assistant.queryOriginal")
        if afterCommit {
            status(language == "en" ? "confirmed receipt" : "确认回执")
            XCTAssertFalse(app.buttons["assistant.resubmit"].exists)
        } else {
            status(language == "en" ? "still be accepted" : "仍可接收")
            tap("assistant.resubmit")
            let beforeConfirm = try await proof(choice, cid)
            XCTAssertEqual(beforeConfirm.posts, 1)
            tap("assistant.confirmResubmit")
            status(language == "en" ? "confirmed receipt" : "确认回执")
        }
        let final = try await proof(choice, cid)
        XCTAssertEqual(final.posts, afterCommit ? 1 : 2); XCTAssertEqual(final.receipts, 1)
        XCTAssertTrue(final.matching_originals); XCTAssertGreaterThanOrEqual(final.status_reads, 1)
        XCTAssertEqual(final.forbidden_writes, 0)
        capture(language + (afterCommit ? "-query-accepted-no-resend" : "-restored-confirmed-exact-original"))
        app.terminate()
    }
    func testUnknownBeforeEnglish() async throws { try await unknown("en", "A", afterCommit: false) }
    func testUnknownBeforeChinese() async throws { try await unknown("zh-Hans", "B", afterCommit: false) }
    func testUnknownAfterEnglish() async throws { try await unknown("en", "A", afterCommit: true) }
    func testUnknownAfterChinese() async throws { try await unknown("zh-Hans", "B", afterCommit: true) }
    func testReleaseClosed() async throws {
        _ = try await call("/normal")
        let before = try await call("/audit")
        let fixture = try JSONDecoder().decode(Fixture.self, from: await call("/config"))
        app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", "en"]
        app.launchEnvironment = ["G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": fixture.endpoint,
                                 "G2C_DEV_ACCOUNTS": String(data: try JSONEncoder().encode(fixture.accounts), encoding: .utf8)!]
        app.launch(); XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        tap("Assistant"); enter("CJ164 release blocked")
        XCTAssertFalse(app.buttons["assistant.send"].exists)
        XCTAssertFalse(app.buttons["assistant.resubmit"].exists)
        let after = try await call("/audit")
        XCTAssertEqual(after, before)
        capture("release-no-send-capability"); app.terminate()
    }
}
