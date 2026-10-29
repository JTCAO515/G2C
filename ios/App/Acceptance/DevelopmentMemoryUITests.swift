import XCTest
import Foundation

@MainActor final class DevelopmentMemoryUITests: XCTestCase {
    let bundle = "space.go2china.memory.acceptance"
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable {
        let endpoint: String
        let accounts: [String: String]
        let subjects: [String: String]
        let profile: String
        let case_id: String
        let conversation: String
    }
    func call(_ path: String, _ values: [String: String] = [:]) async throws -> Data {
        var url = URLComponents(string: control + path)!
        url.queryItems = values.map { URLQueryItem(name: $0.key, value: $0.value) }
        let (bytes, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return bytes
    }
    func tap(_ name: String) {
        let target = app.buttons.matching(identifier: name).firstMatch
        for _ in 0..<10 {
            if target.exists && target.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(target.waitForExistence(timeout: 10), name)
        XCTAssertTrue(target.isHittable, name)
        target.tap()
    }
    func back() { app.navigationBars.buttons.firstMatch.tap() }
    func text(_ identifier: String, _ value: String) {
        let target = app.descendants(matching: .any).matching(identifier: identifier).firstMatch
        XCTAssertTrue(target.waitForExistence(timeout: 10), identifier)
        target.tap(); target.typeText(value)
        if app.buttons["Done"].exists { app.buttons["Done"].tap() }
    }
    func waitStatus(_ value: String) {
        let target = app.staticTexts["memory.save.status"].firstMatch
        let match = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", value), object: target)
        XCTAssertEqual(XCTWaiter.wait(for: [match], timeout: 35), .completed, target.exists ? target.label : "missing status")
    }
    func capture(_ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = name
        image.lifetime = .keepAlways; add(image)
    }
    func launch(_ f: Fixture, language: String, restore: Bool = false, account: String = "A", large: Bool = false) throws {
        app?.terminate(); app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment = ["G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": f.endpoint,
            "G2C_DEV_ACCOUNTS": restore ? "{}" : String(data: try JSONEncoder().encode(f.accounts), encoding: .utf8)!,
            "G2C_DEV_MEMORY_PROFILE": f.profile]
        app.launch()
        tap(language == "en" ? "Memory" : "记忆"); tap("memory.account")
        if restore { tap("account.development.restore") }
        else { tap("account.development.signout"); tap("account.development.signin." + account) }
        let signed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", f.subjects[account]!), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [signed], timeout: 20), .completed)
        back()
    }
    func prepare(_ mode: String) async throws -> Fixture {
        continueAfterFailure = false
        return try JSONDecoder().decode(Fixture.self, from: await call("/prepare", ["mode": mode]))
    }
    func save(_ slot: String, text value: String, language: String) {
        tap("memory.add"); tap("memory.manual.scope")
        tap("self · " + slot + " · Long term / 长期")
        text("memory.manual.text", value)
        text("memory.manual.time", "Synthetic date unknown / 合成时间不详")
        // Dismiss the keyboard without submitting another action.
        app.swipeUp()
        tap("memory.manual.save")
    }
    func query(_ f: Fixture, _ stage: String) async throws {
        _ = try await call("/verify", ["case": f.case_id, "stage": stage])
    }
    func success(language: String, large: Bool = false) async throws {
        let f = try await prepare("success")
        defer { app?.terminate() }
        try launch(f, language: language, large: large)
        let rows = [("fact", "Synthetic fact / 合成事实"), ("experience", "Synthetic experience / 合成经历"), ("food.spice", "cafe\u{301} / 合成偏好")]
        for (slot, value) in rows {
            save(slot, text: value, language: language)
            waitStatus(language == "en" ? "Saved." : "已保存")
            capture("saved-" + slot + "-" + language); back()
        }
        tap(language == "en" ? "Load groups" : "读取分组")
        let group = app.buttons.containing(.staticText, identifier: "self").firstMatch
        XCTAssertTrue(group.waitForExistence(timeout: 10)); group.tap()
        tap(language == "en" ? "Load from start" : "从头读取")
        for (_, value) in rows {
            let item = app.buttons.containing(.staticText, identifier: value).firstMatch
            XCTAssertTrue(item.waitForExistence(timeout: 10)); item.tap()
            tap(language == "en" ? "Load current detail" : "读取当前详情")
            XCTAssertTrue(app.staticTexts[value].waitForExistence(timeout: 10))
            XCTAssertTrue(app.staticTexts["Synthetic date unknown / 合成时间不详"].exists)
            capture("detail-" + language); back()
        }
        try await query(f, "three-saves")
        app.terminate()
        try launch(f, language: language == "en" ? "zh-Hans" : "en", restore: true)
        tap("memory.add"); tap(language == "en" ? "读取原操作" : "Read original operations")
        for _ in 0..<3 {
            let buttons = app.buttons.matching(identifier: language == "en" ? "查询此原操作" : "Query this original operation")
            XCTAssertEqual(buttons.count, 3)
            buttons.element(boundBy: 0).tap()
        }
        capture("reopen-originals"); try await query(f, "reopen")
    }
    func testEnglish() async throws { try await success(language: "en") }
    func testChineseLargeText() async throws { try await success(language: "zh-Hans", large: true) }
    func testUnknownReopen() async throws {
        let f = try await prepare("unknown"); defer { app?.terminate() }
        try launch(f, language: "en")
        save("food.spice", text: "Synthetic ACK loss / 合成回执丢失", language: "en")
        waitStatus("Result unknown"); capture("unknown")
        app.terminate(); try launch(f, language: "en", restore: true)
        tap("memory.add"); tap("Read original operations"); tap("Query this original operation")
        waitStatus("Saved."); capture("original-reconciled")
        try await query(f, "unknown-reopen")
    }
    func testRejected() async throws {
        let f = try await prepare("rejected"); defer { app?.terminate() }
        try launch(f, language: "en")
        save("blocked", text: "Synthetic denied collection", language: "en")
        waitStatus("Save not confirmed"); capture("real-policy-rejected")
        try await query(f, "rejected")
    }
    func testSkipAndChat() async throws {
        let f = try await prepare("skip"); defer { app?.terminate() }
        try launch(f, language: "en")
        tap("memory.collection.open"); capture("optional-questions")
        tap("memory.collection.skip")
        tap("assistant.serverHistory"); tap("history.loadConversations")
        tap("history.conversation." + f.conversation); tap("assistant.panel.done")
        text("assistant.draft", "Synthetic chat after skip")
        tap("assistant.send")
        let completed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", "Completed"), object: app.staticTexts["run.display.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [completed], timeout: 35), .completed)
        capture("chat-after-skip"); try await query(f, "skip")
    }
    func testReleaseClosed() async throws {
        let f = try await prepare("release"); defer { app?.terminate() }
        app = XCUIApplication(bundleIdentifier: bundle)
        app.launchEnvironment = ["G2C_DEV_API_BASE_URL": f.endpoint, "G2C_DEV_TOKEN": f.accounts["A"]!, "G2C_DEV_MEMORY_PROFILE": f.profile]
        app.launch(); tap("Memory"); tap("memory.add")
        XCTAssertTrue(app.staticTexts["Memory is not configured."].exists)
        XCTAssertFalse(app.buttons["memory.manual.save"].exists)
        capture("release-disconnected"); try await query(f, "release")
    }
}
