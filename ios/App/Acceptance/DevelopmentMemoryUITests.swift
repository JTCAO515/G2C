import XCTest
import Foundation

@MainActor final class DevelopmentMemoryUITests: XCTestCase {
    let bundle = "space.go2china.memory.acceptance"
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    struct ReadProof: Decodable {
        struct Item: Decodable { let slot: String; let source_id: String; let item_id: String }
        let items: [Item]
    }
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
        let target: XCUIElement
        if identifier == "memory.manual.text" || identifier == "assistant.draft" { target = app.textViews[identifier] }
        else { target = app.textFields[identifier] }
        XCTAssertTrue(target.waitForExistence(timeout: 10), identifier)
        for _ in 0..<8 {
            if target.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(target.isHittable, identifier)
        target.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        target.typeText(value)
        guard let entered = target.value as? String else { XCTFail("Native input has no text value"); return }
        XCTAssertEqual(Array(entered.utf8), Array(value.utf8))
        if app.buttons["memory.keyboard.done"].exists { app.buttons["memory.keyboard.done"].tap() }
        else if app.buttons["Done"].exists { app.buttons["Done"].tap() }
        else if app.buttons["完成"].exists { app.buttons["完成"].tap() }
    }
    func waitStatus(_ value: String, identifier: String = "memory.save.status") {
        let target = app.staticTexts[identifier].firstMatch
        let match = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", value), object: target)
        XCTAssertEqual(XCTWaiter.wait(for: [match], timeout: 35), .completed, target.exists ? target.label : "missing status")
    }
    func capture(_ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = name
        image.lifetime = .keepAlways; add(image)
    }
    func audit(_ context: String) throws {
        var issues = 0
        continueAfterFailure = true
        defer { continueAfterFailure = false }
        try app.performAccessibilityAudit(for: .all) { issue in
            issues += 1
            print(context, issue.detailedDescription, issue.element?.label ?? "unavailable", issue.element?.frame ?? .zero)
            return false
        }
        continueAfterFailure = false
        XCTAssertEqual(issues, 0)
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
    func prepare(_ mode: String, caseID: String? = nil) async throws -> Fixture {
        continueAfterFailure = false
        var values = ["mode": mode]
        if let caseID { values["case"] = caseID }
        return try JSONDecoder().decode(Fixture.self, from: await call("/prepare", values))
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
        let f = try await prepare("success", caseID: large ? "testChineseLargeText" : "testEnglish")
        defer { app?.terminate() }
        try launch(f, language: language, large: large)
        tap(language == "en" ? "Load groups" : "读取分组")
        XCTAssertTrue(app.staticTexts[language == "en" ? "No memory groups" : "暂无记忆分组"].waitForExistence(timeout: 10))
        capture("empty-" + language)
        let rows = [("fact", "Synthetic fact / 合成事实"), ("experience", "Synthetic experience / 合成经历"), ("food.spice", "cafe\u{301} / 合成偏好")]
        for (slot, value) in rows {
            save(slot, text: value, language: language)
            waitStatus(language == "en" ? "Saved." : "已保存")
            capture("saved-" + slot + "-" + language); back()
        }
        let readProof = try JSONDecoder().decode(ReadProof.self, from: await call("/verify", ["case": f.case_id, "stage": "three-saves"]))
        tap(language == "en" ? "Load groups" : "读取分组")
        let group = app.buttons["memory.group.0"]
        XCTAssertTrue(group.waitForExistence(timeout: 10)); group.tap()
        tap(language == "en" ? "Load from start" : "从头读取")
        for (slot, value) in rows {
            let source = try XCTUnwrap(readProof.items.first { $0.slot == slot })
            let item = app.buttons["memory.item." + source.item_id]
            XCTAssertTrue(item.waitForExistence(timeout: 10)); item.tap()
            tap(language == "en" ? "Load current detail" : "读取当前详情")
            XCTAssertTrue(app.staticTexts[value].waitForExistence(timeout: 10))
            let timeLabel = (language == "en" ? "Approximate time, " : "大致时间, ") + "Synthetic date unknown / 合成时间不详"
            XCTAssertTrue(app.staticTexts[timeLabel].waitForExistence(timeout: 10), app.debugDescription)
            XCTAssertTrue(app.staticTexts[language == "en" ? "Subject, self" : "对象, self"].exists)
            XCTAssertTrue(app.staticTexts[(language == "en" ? "Field, " : "字段, ") + slot].exists)
            XCTAssertTrue(app.staticTexts[language == "en" ? "Scope, long_term" : "范围, long_term"].exists)
            XCTAssertTrue(app.staticTexts[language == "en" ? "Version, 1" : "版本, 1"].exists)
            XCTAssertTrue(app.staticTexts[language == "en" ? "Source version, 1" : "来源版本, 1"].exists)
            XCTAssertTrue(app.staticTexts[(language == "en" ? "Source, " : "来源, ") + source.source_id].exists)
            capture("detail-" + language); try audit("MEMORY_DETAIL_" + language); back()
        }
        back(); tap("memory.language")
        tap(language == "en" ? "简体中文" : "English")
        back()
        let switched = language == "en" ? "zh-Hans" : "en"
        tap(switched == "en" ? "Load groups" : "读取分组")
        tap("memory.group.0"); tap(switched == "en" ? "Load from start" : "从头读取")
        for (slot, value) in rows {
            let source = try XCTUnwrap(readProof.items.first { $0.slot == slot })
            let item = app.buttons["memory.item." + source.item_id]
            XCTAssertTrue(item.waitForExistence(timeout: 10))
            XCTAssertEqual(item.label, value + ", " + (switched == "en" ? "Active" : "已启用"))
        }
        capture("same-records-after-settings-language-change")
        app.terminate()
        try launch(f, language: switched, restore: true)
        tap("memory.add"); tap(language == "en" ? "读取原操作" : "Read original operations")
        for index in 0..<3 {
            let buttons = app.buttons.matching(identifier: language == "en" ? "查询此原操作" : "Query this original operation")
            XCTAssertEqual(buttons.count, 3)
            buttons.element(boundBy: index).tap()
            waitStatus(language == "en" ? "已保存" : "Saved.", identifier: "memory.original.status")
        }
        capture("reopen-originals"); back()
        tap(switched == "en" ? "Load groups" : "读取分组")
        tap("memory.group.0"); tap(switched == "en" ? "Load from start" : "从头读取")
        for (slot, value) in rows {
            let source = try XCTUnwrap(readProof.items.first { $0.slot == slot })
            let item = app.buttons["memory.item." + source.item_id]
            XCTAssertTrue(item.waitForExistence(timeout: 10))
            XCTAssertEqual(item.label, value + ", " + (switched == "en" ? "Active" : "已启用"))
        }
        capture("same-originals-after-language-switch")
        try audit("MEMORY_LIST_" + switched)
        try await query(f, "reopen")
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
        waitStatus("Saved.", identifier: "memory.original.status"); capture("original-reconciled")
        try audit("MEMORY_UNKNOWN_RECOVERED")
        try await query(f, "unknown-reopen")
    }
    func testRejected() async throws {
        let f = try await prepare("rejected"); defer { app?.terminate() }
        try launch(f, language: "en")
        save("blocked", text: "Synthetic denied collection", language: "en")
        waitStatus("Save not confirmed"); capture("real-policy-rejected")
        try audit("MEMORY_REJECTED")
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
    func testCandidate() async throws {
        let f = try await prepare("candidate"); defer { app?.terminate() }
        try launch(f, language: "en")
        save("ambiguous", text: "Synthetic unconfirmed candidate", language: "en")
        waitStatus("Saved as a candidate")
        capture("candidate-not-fact"); back(); tap("Load groups"); tap("memory.group.0"); tap("Load from start")
        XCTAssertTrue(app.staticTexts["Candidate · unconfirmed"].waitForExistence(timeout: 10))
        try await query(f, "candidate")
    }
    func testServerUnknown() async throws {
        let f = try await prepare("server_unknown"); defer { app?.terminate() }
        try launch(f, language: "en")
        _ = try await call("/hold-operation", ["case": f.case_id])
        save("fact", text: "Synthetic precommit auth change", language: "en")
        _ = try await call("/revoke-blocked-operation", ["case": f.case_id])
        waitStatus("Result unknown"); capture("actual-server-unknown")
        _ = try await call("/restore-access", ["case": f.case_id])
        tap("memory.save.query"); waitStatus("Original receipt not observed")
        capture("unknown-null-is-not-retry")
        try await query(f, "server-unknown")
    }
    func testSwitchLateRead() async throws {
        let f = try await prepare("switch"); defer { app?.terminate() }
        try launch(f, language: "en")
        save("fact", text: "Synthetic A private memory", language: "en"); waitStatus("Saved."); back()
        _ = try await call("/hold-read", ["case": f.case_id])
        tap("Load groups"); _ = try await call("/wait-held", ["case": f.case_id])
        XCTAssertTrue(app.staticTexts["Loading memories"].exists)
        tap("memory.account"); tap("account.development.signin.B")
        let signed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", f.subjects["B"]!), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [signed], timeout: 15), .completed)
        back(); _ = try await call("/release-read", ["case": f.case_id])
        XCTAssertFalse(app.buttons["memory.group.0"].exists)
        tap("Load groups"); XCTAssertTrue(app.staticTexts["No memory groups"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["Synthetic A private memory"].exists)
        capture("B-after-A-late-response"); try await query(f, "switch")
    }
    func testRevokedLateRead() async throws {
        let f = try await prepare("revoke"); defer { app?.terminate() }
        try launch(f, language: "en")
        save("fact", text: "Synthetic revoked memory", language: "en"); waitStatus("Saved."); back()
        _ = try await call("/hold-read", ["case": f.case_id])
        tap("Load groups"); _ = try await call("/wait-held", ["case": f.case_id])
        _ = try await call("/revoke-access", ["case": f.case_id])
        XCUIDevice.shared.press(.home); app.activate()
        tap("Memory"); tap("memory.account")
        let rejected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", "Sign-in was rejected"), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [rejected], timeout: 15), .completed)
        _ = try await call("/release-read", ["case": f.case_id])
        back(); XCTAssertFalse(app.buttons["memory.group.0"].exists)
        XCTAssertFalse(app.staticTexts["Synthetic revoked memory"].exists)
        capture("revoked-no-late-content"); try await query(f, "revoke")
    }
    func testReleaseClosed() async throws {
        let f = try await prepare("release"); defer { app?.terminate() }
        app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", "en"]
        app.launchEnvironment = ["G2C_DEV_API_BASE_URL": f.endpoint, "G2C_DEV_TOKEN": f.accounts["A"]!, "G2C_DEV_MEMORY_PROFILE": f.profile]
        app.launch(); tap("Memory"); tap("memory.add")
        XCTAssertTrue(app.staticTexts["Memory is not configured."].exists)
        XCTAssertFalse(app.buttons["memory.manual.save"].exists)
        capture("release-disconnected"); try audit("MEMORY_RELEASE")
        try await query(f, "release")
    }
}
