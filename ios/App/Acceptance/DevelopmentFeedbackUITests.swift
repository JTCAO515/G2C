import XCTest
import Foundation

@MainActor final class DevelopmentFeedbackUITests: XCTestCase {
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable { let endpoint: String; let accounts: [String: String]; let subjects: [String: String]; let case_id: String; let conversation: String; let prompt: String }
    struct Feedback: Decodable { let action_id: String; let sha256: String; let problem: String; let expectation: String; let references: [Reference] }
    struct Reference: Decodable { let kind: String; let id: String }
    struct Account: Decodable { let role: String; let feedback: [Feedback] }
    struct Proof: Decodable { let accounts: [String: Account]; let provider_calls: Int; let feedback_posts: Int }
    @discardableResult func call(_ path: String, _ caseID: String, _ values: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        url.queryItems = values.merging(["case": caseID]) { _, new in new }.map { .init(name: $0.key, value: $0.value) }
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, path)
        return data
    }
    func prepare(_ name: String) async throws -> Fixture {
        continueAfterFailure = false
        return try JSONDecoder().decode(Fixture.self, from: await call("/prepare", name))
    }
    func proof(_ f: Fixture) async throws -> Proof { try JSONDecoder().decode(Proof.self, from: await call("/proof", f.case_id)) }
    func tap(_ id: String) {
        let query = app.buttons.matching(identifier: id), target = app.buttons.matching(identifier: id).element
        for _ in 0..<30 {
            if target.exists && target.isHittable { break }
            let bar = app.navigationBars.firstMatch
            if target.exists && bar.exists && target.frame.midY < bar.frame.maxY { app.swipeDown() }
            else { app.swipeUp() }
        }
        XCTAssertEqual(query.count, 1, id); XCTAssertTrue(target.isHittable, id)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: target)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 20), .completed, id); target.tap()
    }
    func launch(_ f: Fixture, language: String = "en") throws {
        app?.terminate(); app = XCUIApplication(bundleIdentifier: "space.go2china.feedback.acceptance")
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["OS_ACTIVITY_MODE": "disable", "G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": f.endpoint,
            "G2C_DEV_FEEDBACK_PROFILE": "feedback-v1", "G2C_DEV_ACCOUNTS": String(data: try JSONEncoder().encode(f.accounts), encoding: .utf8)!]
        app.launch(); XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts["g2c.dev.error"].exists)
    }
    func account(_ language: String = "en") {
        tap(language == "en" ? "Memory" : "记忆")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
    }
    func signed(_ f: Fixture, _ key: String = "A") {
        let expected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", f.subjects[key]!), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 25), .completed)
    }
    func login(_ f: Fixture, language: String = "en") {
        account(language); tap("account.development.signout"); tap("account.development.signin.A"); signed(f)
    }
    func restore(_ f: Fixture, language: String) {
        account(language); tap("account.development.restore"); signed(f)
    }
    func back() {
        let buttons = app.navigationBars.buttons
        XCTAssertEqual(buttons.count, 1); buttons.element.tap()
    }
    func general(_ language: String = "en", backFromAccount: Bool = false) {
        tap(language == "en" ? "Memory" : "记忆")
        if backFromAccount || app.staticTexts["account.development.status"].exists { back() }
        tap("memory.feedback")
        XCTAssertTrue(app.staticTexts["feedback.status"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.switches["feedback.associate"].exists)
    }
    func status(_ expected: String) {
        let value = app.staticTexts["feedback.status"]
        XCTAssertTrue(value.waitForExistence(timeout: 15))
        let condition = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", expected), object: value)
        XCTAssertEqual(XCTWaiter.wait(for: [condition], timeout: 30), .completed, value.label)
    }
    func fill(_ problem: String, expectation: String) {
        let field = app.textViews["feedback.problem"]
        XCTAssertTrue(field.waitForExistence(timeout: 10)); XCTAssertTrue(field.isEnabled && field.isHittable)
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.1, dy: 0.15)).tap(); field.typeText(problem)
        let next = app.textViews["feedback.expectation"]
        XCTAssertTrue(next.exists); XCTAssertTrue(next.isEnabled && next.isHittable)
        next.coordinate(withNormalizedOffset: CGVector(dx: 0.1, dy: 0.15)).tap(); next.typeText(expectation)
        app.swipeUp() // Form interactive keyboard dismissal; no business action.
    }
    func capture(_ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = name; shot.lifetime = .keepAlways; add(shot)
    }
    func audit(_ name: String, receipt: Bool = false, linked: Bool = false) throws {
        var ids = ["feedback.problem", "feedback.expectation", "feedback.submit", "feedback.status", "feedback.loadPending"]
        if linked && !receipt { ids.append("feedback.associate") }
        if receipt { ids += ["feedback.disclaimer", "feedback.another", "feedback.receipt.date", "feedback.receipt.time"] }
        if linked && receipt { ids += ["feedback.originalref.message", "feedback.originalref.run", "feedback.source.status", "feedback.source.progress", "feedback.source.notice"] }
        for id in ids {
            let query: XCUIElementQuery
            if id == "feedback.problem" || id == "feedback.expectation" { query = app.textViews.matching(identifier: id) }
            else if id == "feedback.associate" { query = app.switches.matching(identifier: id) }
            else if ["feedback.submit", "feedback.loadPending", "feedback.another"].contains(id) { query = app.buttons.matching(identifier: id) }
            else { query = app.descendants(matching: .any).matching(identifier: id) }
            let target = query.element
            for _ in 0..<35 {
                if target.exists && target.isHittable { break }
                let bar = app.navigationBars.firstMatch
                if target.exists && bar.exists && target.frame.midY < bar.frame.maxY { app.swipeDown() }
                else { app.swipeUp() }
            }
            XCTAssertEqual(query.count, 1, id); XCTAssertTrue(target.isHittable, id)
            capture(name + "-" + id)
            continueAfterFailure = true
            var issues = 0
            try app.performAccessibilityAudit(for: .all) { issue in
                issues += 1; print(name, id, issue.detailedDescription, issue.element?.label ?? "unavailable"); return false
            }
            continueAfterFailure = false; XCTAssertEqual(issues, 0)
        }
    }
    func answer(_ f: Fixture, language: String) async throws {
        tap(language == "en" ? "Assistant" : "助手")
        tap("assistant.serverHistory"); tap("history.loadConversations")
        tap("history.conversation." + f.conversation); tap("assistant.panel.done")
        let draft = app.textViews["assistant.draft"]
        XCTAssertTrue(draft.waitForExistence(timeout: 8)); draft.tap(); draft.typeText(f.prompt)
        tap("assistant.send")
        let value = app.staticTexts["run.display.status"]
        let condition = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", language == "en" ? "Completed" : "已完成"), object: value)
        XCTAssertEqual(XCTWaiter.wait(for: [condition], timeout: 40), .completed)
        tap("assistant.feedback")
        XCTAssertTrue(app.switches["feedback.associate"].waitForExistence(timeout: 10))
        let association = app.switches["feedback.associate"]
        XCTAssertEqual(association.value as? String, "0")
        // Only the explicit opt-in sends the original message/run references.
        association.switches.element.tap(); XCTAssertEqual(association.value as? String, "1")
        XCTAssertEqual(app.textViews["feedback.problem"].value as? String, language == "en" ? "Problem" : "问题")
        fill("站名有误 e\u{301} 🌏", expectation: "请核对站名")
        XCTAssertEqual(association.value as? String, "1")
        try audit("answer-editor-" + language, linked: true)
        tap("feedback.submit"); status(language == "en" ? "Feedback submitted." : "反馈已提交。")
        XCTAssertTrue(app.staticTexts["feedback.disclaimer"].exists)
        try audit("answer-receipt-" + language, receipt: true, linked: true)
    }
    func basic(_ name: String, language: String) async throws {
        let f = try await prepare(name); defer { app?.terminate() }
        try launch(f, language: language); login(f, language: language)
        try await answer(f, language: language)
        let first = try await proof(f)
        XCTAssertEqual(first.accounts["A"]?.role, "cj_m1_runtime")
        XCTAssertEqual(first.accounts["A"]?.feedback.count, 1)
        XCTAssertEqual(first.accounts["A"]?.feedback.first?.references.map(\.kind), ["message", "run"])
        XCTAssertEqual(first.accounts["A"]?.feedback.first?.problem, "站名有误 e\u{301} 🌏")
        XCTAssertEqual(first.provider_calls, 1)
        tap("assistant.panel.done")
        general(language)
        XCTAssertEqual(app.textViews["feedback.problem"].value as? String, language == "en" ? "Problem" : "问题")
        fill("记忆页面建议", expectation: "说明更清楚")
        _ = try await call("/size", f.case_id, ["value": "accessibility-extra-extra-extra-large"])
        try audit("general-max-editor-" + language)
        tap("feedback.submit"); status(language == "en" ? "Feedback submitted." : "反馈已提交。")
        try audit("general-max-receipt-" + language, receipt: true)
        let second = try await proof(f)
        XCTAssertEqual(second.accounts["A"]?.feedback.count, 2)
        XCTAssertEqual(second.accounts["A"]?.feedback.last?.references.count, 0)
        XCTAssertEqual(second.provider_calls, first.provider_calls)
        XCTAssertEqual(second.feedback_posts, first.feedback_posts + 1)
        _ = try await call("/validate", f.case_id)
        tap("feedback.another")
        XCTAssertTrue(app.textViews["feedback.problem"].isEnabled)
        status(language == "en" ? "Ready to describe" : "请填写反馈")
        _ = try await call("/size", f.case_id, ["value": "large"])
    }
    func testAnswerAndGeneralEnglish() async throws { try await basic("testAnswerAndGeneralEnglish", language: "en") }
    func testAnswerAndGeneralChinese() async throws { try await basic("testAnswerAndGeneralChinese", language: "zh-Hans") }
    func testUnknownReopenAndOriginalLookup() async throws {
        let f = try await prepare("testUnknownReopenAndOriginalLookup"); defer { app?.terminate() }
        try launch(f); login(f); general(backFromAccount: true)
        fill("回执丢失后保留原反馈", expectation: "只查询原动作")
        _ = try await call("/fault", f.case_id, ["kind": "drop"])
        tap("feedback.submit"); status("Submission is not confirmed")
        let before = try await proof(f), original = try XCTUnwrap(before.accounts["A"]?.feedback.first)
        XCTAssertEqual(before.accounts["A"]?.feedback.count, 1)
        XCTAssertFalse(app.buttons["feedback.submit"].isEnabled)
        try audit("unknown-original-retained")
        try launch(f, language: "zh-Hans"); restore(f, language: "zh-Hans")
        general("zh-Hans", backFromAccount: true)
        tap("feedback.loadPending"); tap("feedback.pending." + original.action_id)
        XCTAssertEqual(app.textViews["feedback.problem"].value as? String, "回执丢失后保留原反馈")
        XCTAssertFalse(app.textViews["feedback.problem"].isEnabled)
        status("提交结果尚未确认")
        tap("feedback.query"); status("反馈已提交。")
        let after = try await proof(f)
        XCTAssertEqual(after.accounts["A"]?.feedback.first?.sha256, original.sha256)
        XCTAssertEqual(after.feedback_posts, before.feedback_posts)
        XCTAssertEqual(after.provider_calls, before.provider_calls)
        try audit("reopened-original-confirmed-chinese", receipt: true)
        _ = try await call("/validate", f.case_id)
    }
    func testLateACKAccountSwitch() async throws {
        let f = try await prepare("testLateACKAccountSwitch"); defer { app?.terminate() }
        try launch(f); login(f); general(backFromAccount: true)
        fill("旧账号的迟到反馈", expectation: "不能进入新账号")
        _ = try await call("/fault", f.case_id, ["kind": "hold"])
        tap("feedback.submit")
        let before = try JSONDecoder().decode(Proof.self, from: await call("/wait-held", f.case_id))
        XCTAssertEqual(before.accounts["A"]?.feedback.count, 1)
        back(); account(); tap("account.development.signin.B"); signed(f, "B")
        _ = try await call("/release", f.case_id)
        general(backFromAccount: true); status("Ready to describe")
        XCTAssertFalse(app.staticTexts["feedback.disclaimer"].exists)
        XCTAssertFalse(app.textViews["feedback.problem"].value as? String == "旧账号的迟到反馈")
        tap("feedback.loadPending")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "feedback.pending.")).count, 0)
        let after = try await proof(f)
        XCTAssertEqual(after.accounts["B"]?.feedback.count, 0)
        XCTAssertEqual(after.feedback_posts, before.feedback_posts)
        try audit("new-account-no-old-feedback")
        _ = try await call("/validate", f.case_id)
    }
}
