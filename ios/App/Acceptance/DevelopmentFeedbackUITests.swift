import XCTest
import Foundation

@MainActor final class DevelopmentFeedbackUITests: XCTestCase {
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    #if G2C_M4_DEVICE_ACCEPTANCE
    private lazy var deviceSession = M4DeviceTestSession(test: self, control: control)
    #endif
    struct Fixture: Decodable { let endpoint: String; let accounts: [String: String]; let subjects: [String: String]; let case_id: String; let conversation: String; let prompt: String }
    struct Feedback: Decodable { let action_id: String; let sha256: String; let problem: String; let expectation: String; let references: [Reference] }
    struct Reference: Decodable { let kind: String; let id: String }
    struct Account: Decodable { let role: String; let feedback: [Feedback] }
    struct Proof: Decodable { let accounts: [String: Account]; let provider_calls: Int; let feedback_posts: Int }
    @discardableResult func call(_ path: String, _ caseID: String, _ values: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        url.queryItems = values.merging(["case": caseID]) { _, new in new }.map { .init(name: $0.key, value: $0.value) }
        #if G2C_M4_DEVICE_ACCEPTANCE
        let (data, response) = try await deviceSession.data(from: XCTUnwrap(url.url))
        #else
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        #endif
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, path)
        return data
    }
    func prepare(_ name: String) async throws -> Fixture {
        continueAfterFailure = false
        return try JSONDecoder().decode(Fixture.self, from: await call("/prepare", name))
    }
    func proof(_ f: Fixture) async throws -> Proof { try JSONDecoder().decode(Proof.self, from: await call("/proof", f.case_id)) }
    func tap(_ id: String) {
        let tabs = ["Assistant", "助手", "Trips", "行程", "Plugins", "插件", "Memory", "记忆"]
        let query = tabs.contains(id) ? app.tabBars.buttons.matching(identifier: id) : app.buttons.matching(identifier: id)
        let target = query.element
        let isChrome = tabs.contains(id) || app.navigationBars.buttons.matching(identifier: id).count == 1
        func viewport() -> (CGFloat, CGFloat) {
            let bar = app.navigationBars.firstMatch, tabs = app.tabBars.firstMatch
            var top = bar.exists ? bar.frame.maxY : app.frame.minY + 60
            var bottom = tabs.exists ? tabs.frame.minY : app.frame.maxY - 20
            if !bar.exists && !["assistant.draft", "assistant.send", "assistant.intent"].contains(id) {
                let header = app.otherElements["assistant.header"], composer = app.otherElements["assistant.composer"]
                if header.exists { top = max(top, header.frame.maxY + 8) }
                if composer.exists { bottom = min(bottom, composer.frame.minY) }
            }
            return (top + 8, bottom - 8)
        }
        // Reuse the accepted typed-memory bounded-drag pattern. Full-window
        // flicks overshoot tall English rows and can land on navigation chrome.
        for attempt in 0..<40 {
            let (top, bottom) = viewport()
            let frame = target.exists ? target.frame : .zero
            if target.exists && target.isHittable && (isChrome || (frame.minY >= top && frame.maxY <= bottom)) { break }
            let located = !frame.isEmpty && frame.minY.isFinite && frame.maxY.isFinite
            let down = located ? frame.minY < top : (attempt / 6) % 2 == 1
            let middle = (top + bottom) / 2, halfStep = min(100, (bottom - top) * 0.15)
            let start = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: app.frame.width * 0.85, dy: middle + (down ? -halfStep : halfStep)))
            let end = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: app.frame.width * 0.85, dy: middle + (down ? halfStep : -halfStep)))
            start.press(forDuration: 0.05, thenDragTo: end)
        }
        XCTAssertEqual(query.count, 1, id); XCTAssertTrue(target.isHittable, id)
        let (top, bottom) = viewport()
        XCTAssertTrue(isChrome || (target.frame.minY >= top && target.frame.maxY <= bottom), id)
        print("feedback tap", id, target.frame)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: target)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 20), .completed, id)
        // XCTest selected a cell-edge activation point for a partially exposed
        // multiline button. Use the resolved, fully visible control's center.
        target.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        #if G2C_M4_DEVICE_ACCEPTANCE
        if id.hasPrefix("account.development.signin.") || id == "account.development.restore" {
            deviceSession.waitForAppNetworkConsent()
        }
        #endif
    }
    func inputQuery(_ id: String) -> XCUIElementQuery {
        #if G2C_M4_DEVICE_ACCEPTANCE
        return deviceSession.textInputQuery(id, in: app)
        #else
        return app.textViews.matching(identifier: id)
        #endif
    }
    func revealEditor(_ id: String) -> XCUIElement {
        let query = inputQuery(id), field = query.element
        #if G2C_M4_DEVICE_ACCEPTANCE
        deviceSession.revealControl(field, in: app, diagnosticIdentifier: id)
        #else
        // General feedback's native Form virtualizes offscreen editors after a
        // completed receipt or pending selection. Read the same editor after scrolling.
        for _ in 0..<6 {
            if field.exists && field.isHittable { break }
            app.swipeDown()
        }
        for _ in 0..<10 {
            if field.exists && field.isHittable { break }
            app.swipeUp()
        }
        #endif
        XCTAssertEqual(query.count, 1, id)
        XCTAssertTrue(field.exists && field.isHittable, id)
        return field
    }
    func launch(_ f: Fixture, language: String = "en") async throws {
        app?.terminate(); app = XCUIApplication(bundleIdentifier: "space.go2china.feedback.acceptance")
        app.launchArguments = ["-cj.ui.language.v1", language]
        #if G2C_M4_DEVICE_ACCEPTANCE
        let accountsJSON = "{}"
        try await deviceSession.stageAccounts(caseID: f.case_id)
        #else
        let accountsJSON = String(data: try JSONEncoder().encode(f.accounts), encoding: .utf8)!
        #endif
        app.launchEnvironment = ["OS_ACTIVITY_MODE": "disable", "G2C_DEV_ACCOUNT_MODE": "1", "G2C_DEV_API_BASE_URL": f.endpoint,
            "G2C_DEV_FEEDBACK_PROFILE": "feedback-v1", "G2C_DEV_ACCOUNTS": accountsJSON]
        #if G2C_M4_DEVICE_ACCEPTANCE
        app.launchEnvironment.merge(try deviceSession.applicationEnvironment(endpoint: f.endpoint, injecting: true)) { _, value in value }
        #endif
        app.launch(); XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts["g2c.dev.error"].exists)
    }
    func account(_ language: String = "en") {
        tap(language == "en" ? "Memory" : "记忆")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
    }
    func signed(_ f: Fixture, _ key: String = "A") {
        #if G2C_M4_DEVICE_ACCEPTANCE
        deviceSession.requireAccount(f.subjects[key]!,in:app)
        #endif
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
        let field = revealEditor("feedback.problem")
        XCTAssertTrue(field.waitForExistence(timeout: 10)); XCTAssertTrue(field.isEnabled && field.isHittable)
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.1, dy: 0.15)).tap(); field.typeText(problem)
        let next = revealEditor("feedback.expectation")
        XCTAssertTrue(next.exists); XCTAssertTrue(next.isEnabled && next.isHittable)
        next.coordinate(withNormalizedOffset: CGVector(dx: 0.1, dy: 0.15)).tap(); next.typeText(expectation)
        let done = app.buttons["feedback.keyboard.done"]
        XCTAssertTrue(done.waitForExistence(timeout: 8)); done.tap()
        XCTAssertFalse(app.keyboards.element.exists)
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
            if id == "feedback.problem" || id == "feedback.expectation" { query = inputQuery(id) }
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
        let inputs = inputQuery("assistant.draft")
        let draft = inputs.element
        XCTAssertTrue(draft.waitForExistence(timeout: 8)); XCTAssertEqual(inputs.count, 1)
        XCTAssertTrue(draft.isEnabled && draft.isHittable)
        draft.tap(); draft.typeText(f.prompt)
        XCTAssertEqual(Array((draft.value as? String ?? "").utf8), Array(f.prompt.utf8))
        #if G2C_M4_DEVICE_ACCEPTANCE
        // Finish the real keyboard interaction before resolving the send button.
        // Its old center can lie under the keyboard accessory after layout moves.
        let done = app.toolbars.buttons.matching(NSPredicate(format: "label == %@", language == "en" ? "Done" : "完成"))
        XCTAssertTrue(done.element.waitForExistence(timeout: 8)); XCTAssertEqual(done.count, 1)
        XCTAssertTrue(done.element.isEnabled && done.element.isHittable); done.element.tap()
        let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 10), .completed)
        #endif
        tap("assistant.send")
        let value = app.staticTexts["run.display.status"]
        let condition = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", language == "en" ? "Completed" : "已完成"), object: value)
        let completed = await XCTWaiter.fulfillment(of: [condition], timeout: 40)
        if completed != .completed {
            capture("feedback-answer-not-completed")
            let tree = XCTAttachment(string: app.debugDescription)
            tree.name = "PRIVATE-feedback-answer-not-completed-tree"; tree.lifetime = .keepAlways; add(tree)
        }
        XCTAssertEqual(completed, .completed)
        tap("assistant.feedback")
        XCTAssertTrue(app.switches["feedback.associate"].waitForExistence(timeout: 10))
        let association = app.switches["feedback.associate"]
        XCTAssertEqual(association.value as? String, "0")
        // Only the explicit opt-in sends the original message/run references.
        association.switches.element.tap(); XCTAssertEqual(association.value as? String, "1")
        XCTAssertEqual(revealEditor("feedback.problem").value as? String, language == "en" ? "Problem" : "问题")
        fill("站名有误 e\u{301} 🌏", expectation: "请核对站名")
        XCTAssertEqual(association.value as? String, "1")
        try audit("answer-editor-" + language, linked: true)
        tap("feedback.submit"); status(language == "en" ? "Feedback submitted." : "反馈已提交。")
        XCTAssertTrue(app.staticTexts["feedback.disclaimer"].exists)
        try audit("answer-receipt-" + language, receipt: true, linked: true)
    }
    func basic(_ name: String, language: String) async throws {
        let f = try await prepare(name); defer { app?.terminate() }
        try await launch(f, language: language); login(f, language: language)
        try await answer(f, language: language)
        let first = try await proof(f)
        XCTAssertEqual(first.accounts["A"]?.role, "cj_m1_runtime")
        XCTAssertEqual(first.accounts["A"]?.feedback.count, 1)
        XCTAssertEqual(first.accounts["A"]?.feedback.first?.references.map(\.kind), ["message", "run"])
        XCTAssertEqual(first.accounts["A"]?.feedback.first?.problem, "站名有误 e\u{301} 🌏")
        XCTAssertEqual(first.provider_calls, 1)
        tap("assistant.panel.done")
        general(language)
        XCTAssertEqual(revealEditor("feedback.problem").value as? String, language == "en" ? "Problem" : "问题")
        fill("记忆页面建议", expectation: "说明更清楚")
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
        // Reset removes the receipt section; the new status row can be virtualized
        // below the long English introduction at system maximum type size.
        for _ in 0..<10 {
            if app.staticTexts["feedback.status"].exists { break }
            app.swipeUp()
        }
        status(language == "en" ? "Ready to describe" : "请填写反馈")
        XCTAssertTrue(revealEditor("feedback.problem").isEnabled)
    }
    func testAnswerAndGeneralEnglish() async throws { try await basic("testAnswerAndGeneralEnglish", language: "en") }
    func testAnswerAndGeneralChinese() async throws { try await basic("testAnswerAndGeneralChinese", language: "zh-Hans") }
    func testUnknownReopenAndOriginalLookup() async throws {
        let f = try await prepare("testUnknownReopenAndOriginalLookup"); defer { app?.terminate() }
        try await launch(f); login(f); general(backFromAccount: true)
        fill("回执丢失后保留原反馈", expectation: "只查询原动作")
        _ = try await call("/fault", f.case_id, ["kind": "drop"])
        tap("feedback.submit"); status("Submission is not confirmed")
        let before = try await proof(f), original = try XCTUnwrap(before.accounts["A"]?.feedback.first)
        XCTAssertEqual(before.accounts["A"]?.feedback.count, 1)
        XCTAssertFalse(app.buttons["feedback.submit"].isEnabled)
        try audit("unknown-original-retained")
        try await launch(f, language: "zh-Hans"); restore(f, language: "zh-Hans")
        general("zh-Hans", backFromAccount: true)
        tap("feedback.loadPending"); tap("feedback.pending." + original.action_id)
        XCTAssertEqual(revealEditor("feedback.problem").value as? String, "回执丢失后保留原反馈")
        XCTAssertFalse(inputQuery("feedback.problem").element.isEnabled)
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
        try await launch(f); login(f); general(backFromAccount: true)
        fill("旧账号的迟到反馈", expectation: "不能进入新账号")
        _ = try await call("/fault", f.case_id, ["kind": "hold"])
        tap("feedback.submit")
        let before = try JSONDecoder().decode(Proof.self, from: await call("/wait-held", f.case_id))
        XCTAssertEqual(before.accounts["A"]?.feedback.count, 1)
        back(); account(); tap("account.development.signin.B"); signed(f, "B")
        _ = try await call("/release", f.case_id)
        general(backFromAccount: true); status("Ready to describe")
        XCTAssertFalse(app.staticTexts["feedback.disclaimer"].exists)
        XCTAssertFalse(revealEditor("feedback.problem").value as? String == "旧账号的迟到反馈")
        tap("feedback.loadPending")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "feedback.pending.")).count, 0)
        let after = try await proof(f)
        XCTAssertEqual(after.accounts["B"]?.feedback.count, 0)
        XCTAssertEqual(after.feedback_posts, before.feedback_posts)
        try audit("new-account-no-old-feedback")
        _ = try await call("/validate", f.case_id)
    }
}
