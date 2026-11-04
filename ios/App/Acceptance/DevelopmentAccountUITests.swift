import XCTest
import Foundation

@MainActor final class DevelopmentAccountUITests: XCTestCase {
    private let bundle = "space.go2china.accounts.acceptance"
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    #if G2C_M4_DEVICE_ACCEPTANCE
    private lazy var deviceSession = M4DeviceTestSession(test: self, control: control)
    #endif
    private struct Fixture: Decodable {
        let endpoint: String
        let accounts: [String: String]
        let subjects: [String: String]
    }

    private func call(_ path: String) async throws -> Data {
        #if G2C_M4_DEVICE_ACCEPTANCE
        let (data, response) = try await deviceSession.data(path)
        #else
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(URL(string: control + path)))
        #endif
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return data
    }

    private func configuration() async throws -> Fixture {
        try JSONDecoder().decode(Fixture.self, from: await call("/config"))
    }

    private func launch(_ fixture: Fixture, language: String, tokens: Bool = true) async throws {
        continueAfterFailure = false
        app?.terminate()
        app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": fixture.endpoint,
                                 "G2C_DEV_TOKEN": "", "G2C_DEV_ACCOUNTS": "{}", "OS_ACTIVITY_MODE": "disable"]
        #if G2C_M4_DEVICE_ACCEPTANCE
        if tokens { try await deviceSession.stageAccounts() }
        app.launchEnvironment.merge(try deviceSession.applicationEnvironment(
            endpoint: fixture.endpoint, injecting: tokens)) { _, value in value }
        #else
        if tokens {
            app.launchEnvironment["G2C_DEV_ACCOUNTS"] = String(data: try JSONEncoder().encode(fixture.accounts), encoding: .utf8)
        }
        #endif
        app.launch()
        #if G2C_M4_DEVICE_ACCEPTANCE
        for _ in 0..<8 {
            deviceSession.handleAppConsent()
            try await Task.sleep(for: .milliseconds(500))
        }
        #endif
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        account(language)
    }

    private func tap(_ id: String) {
        let button = app.buttons.matching(identifier: id).firstMatch
        XCTAssertTrue(button.waitForExistence(timeout: 5), id)
        if !button.isHittable { app.swipeUp() }
        XCTAssertTrue(button.isHittable, id)
        button.tap()
    }

    private func account(_ language: String) {
        tap(language == "en" ? "Memory" : "记忆")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
    }

    private func state(_ value: String) {
        let node = app.staticTexts["account.development.status"]
        XCTAssertTrue(node.waitForExistence(timeout: 5))
        let wait = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", value), object: node)
        let result = XCTWaiter.wait(for: [wait], timeout: 15)
        XCTAssertEqual(result, .completed, "Expected account state: " + value + "; observed: " + node.label)
    }

    private func signed(_ fixture: Fixture, _ account: String, _ language: String) throws {
        let subject = try XCTUnwrap(fixture.subjects[account])
        state(language == "en" ? "Signed in as " + subject : "已登录：" + subject)
    }

    private func signedOut(_ language: String) { state(language == "en" ? "Signed out" : "未登录") }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }

    private func enterDraft(_ language: String) {
        tap(language == "en" ? "Assistant" : "助手")
        let field = app.descendants(matching: .any).matching(identifier: "assistant.draft").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap(); field.typeText("CJ161 private draft")
        XCTAssertEqual(field.value as? String, "CJ161 private draft")
        if app.buttons["Done"].exists { tap("Done") }
        else if app.buttons["完成"].exists { tap("完成") }
    }

    private func draftCleared(_ language: String) {
        tap(language == "en" ? "Assistant" : "助手")
        let field = app.descendants(matching: .any).matching(identifier: "assistant.draft").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        XCTAssertNotEqual(field.value as? String, "CJ161 private draft")
        XCTAssertFalse(app.staticTexts["CJ161 private draft"].exists)
        account(language)
    }

    private func lifecycle(_ language: String) async throws {
        _ = try await call("/normal")
        let fixture = try await configuration()
        try await launch(fixture, language: language)
        tap("account.development.signout"); signedOut(language)
        for choice in ["A", "B"] {
            tap("account.development.signin." + choice); try signed(fixture, choice, language)
            if choice == "B" { draftCleared(language) }
            enterDraft(language); account(language)
            tap("account.development.signout"); signedOut(language); draftCleared(language)
            tap("account.development.signin." + choice); try signed(fixture, choice, language)
            try await launch(fixture, language: language, tokens: false)
            signedOut(language) // no automatic restoration or injected credential
            tap("account.development.restore"); try signed(fixture, choice, language)
            capture(language + "-keychain-restored-" + choice)
            try await launch(fixture, language: language)
            tap("account.development.restore"); try signed(fixture, choice, language)
            enterDraft(language); account(language)
        }
        tap("account.development.signout"); signedOut(language); draftCleared(language)
        try await launch(fixture, language: language, tokens: false)
        tap("account.development.restore"); signedOut(language)
        capture(language + "-logout-marker")
        app.terminate()
    }

    func testLifecycleEnglish() async throws { try await lifecycle("en") }
    func testLifecycleChinese() async throws { try await lifecycle("zh-Hans") }

    private func deletionEntry(_ language: String) async throws {
        defer { app?.terminate() }
        _ = try await call("/normal")
        let fixture = try await configuration()
        try await launch(fixture, language: language)
        tap("account.development.signout"); signedOut(language)
        tap("account.development.signin.A"); try signed(fixture, "A", language)
        let links = app.buttons.matching(identifier: "account.deletion.open")
        XCTAssertEqual(links.count, 1)
        XCTAssertTrue(links.element.isHittable)
        links.element.tap()
        let status = app.staticTexts["account.deletion.unavailable"]
        XCTAssertTrue(status.waitForExistence(timeout: 5))
        XCTAssertEqual(status.label, language == "en" ? "Account deletion is not available yet. No deletion request has been sent." : "账号注销尚未开放，未发送注销请求。")
        try app.performAccessibilityAudit(for: .all) { issue in
                print("AX_DELETION: \(issue.compactDescription); element=\(issue.element?.label ?? "<unavailable>"); id=\(issue.element?.identifier ?? "<none>")")
                return false
            }
        capture("signed-account-deletion-" + language)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        try signed(fixture, "A", language)
    }

    func testDeletionEntryEnglish() async throws { try await deletionEntry("en") }
    func testDeletionEntryChinese() async throws { try await deletionEntry("zh-Hans") }

    private func failures(_ language: String) async throws {
        _ = try await call("/normal")
        let fixture = try await configuration()
        try await launch(fixture, language: language)
        tap("account.development.signout")
        tap("account.development.signin.Denied")
        state(language == "en" ? "Sign-in was rejected. Check the account and try again." : "登录被拒绝，请核对账号后重试。")
        capture(language + "-rejected")
        tap("account.development.signin.Expired")
        state(language == "en" ? "This session has expired. Sign in again." : "会话已过期，请重新登录。")
        capture(language + "-expired")
        tap("account.development.signin.A"); try signed(fixture, "A", language)
        _ = try await call("/offline")
        tap("account.development.restore")
        state(language == "en" ? "Cannot verify the session right now. Saved credentials have been kept." : "暂时无法验证会话，已保留保存的凭据。")
        capture(language + "-offline-unknown")
        _ = try await call("/online")
        try await launch(fixture, language: language, tokens: false)
        tap("account.development.restore"); try signed(fixture, "A", language)
        capture(language + "-credential-preserved")
        app.terminate()
    }

    func testFailuresEnglish() async throws { try await failures("en") }
    func testFailuresChinese() async throws { try await failures("zh-Hans") }

    private func late(_ language: String) async throws {
        _ = try await call("/normal")
        let fixture = try await configuration()
        try await launch(fixture, language: language)
        tap("account.development.signin.A"); try signed(fixture, "A", language)
        enterDraft(language); account(language)
        _ = try await call("/hold")
        tap("account.development.restore")
        let held = try JSONDecoder().decode([String: Bool].self, from: await call("/wait-held"))
        XCTAssertEqual(held["held"], true)
        tap("account.development.signin.B"); try signed(fixture, "B", language)
        _ = try await call("/release")
        draftCleared(language); try signed(fixture, "B", language)
        try await launch(fixture, language: language, tokens: false)
        tap("account.development.restore"); try signed(fixture, "B", language)
        capture(language + "-late-A-cannot-replace-B")
        app.terminate()
    }

    func testLateEnglish() async throws { try await late("en") }
    func testLateChinese() async throws { try await late("zh-Hans") }

    func testReleaseRemainsDisconnected() async throws {
        _ = try await call("/normal")
        let before = try await call("/audit")
        let fixture = try await configuration()
        try await launch(fixture, language: "en")
        XCTAssertFalse(app.staticTexts["account.development.status"].exists)
        XCTAssertFalse(app.buttons["account.development.restore"].exists)
        let after = try await call("/audit")
        XCTAssertEqual(after, before)
        capture("release-no-development-session")
        app.terminate()
    }
}
