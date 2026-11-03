import XCTest
import Foundation

/// Only observes actual public API replies/files. No source/action/receipt is
/// injected into the App or its current MESSAGE selection.
@MainActor final class MemoryCandidateUITests: XCTestCase {
    let control = "__CONTROL_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable {
        let bundle: String
        let launch: [String: String]
        let subjects: [String: String]
        let conversation: String
        let original_text: String
        let edited_text: String
        let occurred_at: String
        let travel_id: String?
        let travel_version: Int?
    }
    struct Projection: Decodable {
        struct Row: Decodable { let candidate_id: String; let text: String; let status: String }
        let conversation_id: String
        let candidates: [Row]
    }
    struct Proof: Decodable {
        struct Item: Decodable {
            struct Command: Decodable { let text: String }
            let status: String
            let command: Command
        }
        let item_http_status: Int
        let item: Item?
        let candidate_files: [String: String]
        let memory_files: [String: String]
        let action_count: Int
        let action_id: String?
        let input_sha256: String?
        let other_item_unchanged: Bool
    }
    func call(_ path: String, _ query: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        if !query.isEmpty { url.queryItems = query.sorted(by: { $0.key < $1.key }).map { .init(name: $0.key, value: $0.value) } }
        let session = URLSession(configuration: .ephemeral); defer { session.invalidateAndCancel() }
        let (data, response) = try await session.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return data
    }
    func proof() async throws -> Proof { try JSONDecoder().decode(Proof.self, from: await call("/proof")) }
    func reveal(_ element: XCUIElement, centered: Bool = false) {
        func top() -> CGFloat {
            let bars = app.navigationBars.matching(NSPredicate(format: "identifier IN %@", ["Memory suggestions", "记忆建议", "Review suggestion", "核对建议", "Delete account", "注销账号"]))
            XCTAssertEqual(bars.count, 1)
            return bars.element.frame.maxY
        }
        for index in 0..<100 {
            if element.exists && element.isHittable && (!centered || (element.frame.midY > top() && element.frame.midY < app.frame.maxY - 44)) { return }
            if centered && element.exists {
                if element.frame.midY <= top() { app.swipeDown() } else { app.swipeUp() }
            } else if index < 40 { app.swipeUp() } else { app.swipeDown() }
        }
        print("CANDIDATE_UI_TREE", app.debugDescription)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "candidate-missing-control"; shot.lifetime = .keepAlways; add(shot)
        XCTFail("The exact candidate control is not visible")
    }
    func tap(_ id: String) {
        let label = ["Memory", "记忆", "Assistant", "助手", "Preference", "偏好"].contains(id)
        let query = app.buttons.matching(NSPredicate(format: label ? "label == %@" : "identifier == %@", id)), button = query.element
        reveal(button, centered: id.hasPrefix("memoryCandidate.") || id.hasPrefix("account.cleanup."))
        XCTAssertEqual(query.count, 1, id)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 25), .completed, id)
        button.tap()
    }
    func text(_ id: String, contains value: String) {
        let element = app.staticTexts.matching(identifier: id).element
        var result = XCTWaiter.Result.timedOut
        for _ in 0..<3 {
            reveal(element)
            let expected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", value), object: element)
            result = XCTWaiter.wait(for: [expected], timeout: 10)
            if result == .completed { break }
        }
        if result != .completed { print("CANDIDATE_STATUS", id, element.exists ? element.label : "missing") }
        XCTAssertEqual(result, .completed, id)
    }
    func enter(_ id: String, value: String) {
        let multi = app.textViews.matching(identifier: id), single = app.textFields.matching(identifier: id)
        let query = multi.element.exists ? multi : single, field = query.element
        reveal(field); XCTAssertEqual(query.count, 1)
        field.tap()
        XCTAssertTrue(app.keyboards.element.waitForExistence(timeout: 10), "The actual editor must acquire keyboard focus")
        let old = field.value as? String ?? ""
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count))
        field.typeText(value)
        XCTAssertEqual(Array((field.value as? String ?? "").utf8), Array(value.utf8))
    }
    func audit(_ name: String, target: XCUIElement) throws {
        reveal(target); XCTAssertTrue(target.isHittable)
        continueAfterFailure = true
        var count = 0
        try app.performAccessibilityAudit(for: .all) { issue in
            count += 1; print(name, issue.detailedDescription, issue.element?.identifier ?? "unavailable"); return false
        }
        continueAfterFailure = false; XCTAssertEqual(count, 0)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = name; shot.lifetime = .keepAlways; add(shot)
    }
    func signIn(_ fixture: Fixture, _ language: String) {
        tap(language == "en" ? "Memory" : "记忆"); tap("memory.account"); tap("account.development.signin.A")
        guard let subject = fixture.subjects["A"] else { XCTFail("Actual signed local account required"); return }
        text("account.development.status", contains: subject)
        let back = app.navigationBars.buttons.matching(NSPredicate(format: "label == %@", language == "en" ? "Memory" : "记忆"))
        XCTAssertEqual(back.count, 1); back.element.tap()
    }
    func selectConversation(_ fixture: Fixture, _ language: String) {
        tap(language == "en" ? "Assistant" : "助手"); tap("assistant.serverHistory"); tap("history.loadConversations")
        tap("history.conversation." + fixture.conversation); tap("assistant.panel.done")
    }
    func reviewPanel(_ fixture: Fixture) {
        tap("assistant.memoryCandidates.review")
        text("memoryCandidate.conversation", contains: fixture.conversation)
    }
    func verify(_ language: String, operation: String = "confirm", reopen: Bool = false, account: Bool = false, current: Bool = false) async throws {
        continueAfterFailure = false
        let name = (account ? "account-" : reopen ? "lost-ack-" : current ? "current-" : operation + "-") + language
        let f = try JSONDecoder().decode(Fixture.self, from: await call("/fixture", ["case": name]))
        _ = try await call("/size", ["value": "standard"])
        app = XCUIApplication(bundleIdentifier: f.bundle); app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = f.launch.merging(["OS_ACTIVITY_MODE": "disable"]) { _, required in required }
        app.launch(); defer { app.terminate() }
        XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 30)); signIn(f, language)
        selectConversation(f, language); tap("assistant.memoryCandidates.read")
        text("assistant.memoryCandidates.first", contains: f.original_text)
        let projection = try JSONDecoder().decode(Projection.self, from: await call("/observed-projection"))
        XCTAssertEqual(projection.conversation_id, f.conversation); XCTAssertEqual(projection.candidates.count, 1)
        let candidate = try XCTUnwrap(projection.candidates.first)
        let candidateSelector = "memoryCandidate.review." + Data(candidate.candidate_id.utf8).base64EncodedString()
        XCTAssertEqual(candidate.text, f.original_text); XCTAssertEqual(candidate.status, "candidate")
        let before = try await proof(); XCTAssertEqual(before.action_count, 0); XCTAssertEqual(before.item?.status, "candidate")
        reviewPanel(f)
        tap(candidateSelector)
        if operation == "confirm" {
            reveal(app.buttons["memoryCandidate.editor.confirm"])
            XCTAssertFalse(app.buttons["memoryCandidate.editor.confirm"].isEnabled, "An inference requires an explicit concrete kind")
            let kind = app.descendants(matching: .any).matching(identifier: "memoryCandidate.editor.kind")
            reveal(kind.element); XCTAssertEqual(kind.count, 1); kind.element.tap()
            tap(language == "en" ? "Preference" : "偏好")
            enter("memoryCandidate.editor.text", value: f.edited_text)
            enter("memoryCandidate.editor.time", value: f.occurred_at)
            let done = app.toolbars.buttons.matching(identifier: "memoryCandidate.editor.done")
            XCTAssertEqual(done.count, 1); done.element.tap()
            let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.element)
            XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 10), .completed)
        }
        _ = try await call("/size", ["value": "max"])
        text("memoryCandidate.editor.scope", contains: language == "en" ? "other history" : "其他历史")
        if let travelID = f.travel_id, let version = f.travel_version {
            reveal(app.buttons["memoryCandidate.editor.confirm"])
            XCTAssertFalse(app.buttons["memoryCandidate.editor.confirm"].isEnabled, "A candidate's old travel projection is not a fresh read")
            tap("memoryCandidate.editor.readTravel")
            text("memoryCandidate.editor.travel", contains: travelID + " · " + String(version))
        }
        let actionButton = operation == "confirm" ? "memoryCandidate.editor.confirm" : "memoryCandidate.editor.reject"
        try audit("candidate-editor-" + language + "-max", target: app.buttons[actionButton])
        tap(actionButton)
        let original = app.staticTexts["memoryCandidate.originalID"]; reveal(original); let actionID = original.label
        XCTAssertFalse(actionID.isEmpty)
        if reopen {
            text("memoryCandidate.status", contains: language == "en" ? "uncertain" : "尚不明确")
            app.terminate(); app.launch(); XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 30))
            signIn(f, language); selectConversation(f, language); reviewPanel(f)
            tap("memoryCandidate.loadOriginals"); tap("memoryCandidate.original." + actionID)
            text("memoryCandidate.originalID", contains: actionID); tap("memoryCandidate.query")
        }
        text("memoryCandidate.historicalNotice", contains: language == "en" ? "does not prove" : "不代表")
        text("memoryCandidate.receiptResult", contains: operation == "confirm" ? (language == "en" ? "confirmed" : "已确认") : (language == "en" ? "rejected" : "已拒绝"))
        text("memoryCandidate.empty", contains: language == "en" ? "no suggestions" : "没有待确认建议")
        let after = try await proof()
        XCTAssertEqual(after.action_count, 1); XCTAssertEqual(after.action_id, actionID)
        XCTAssertEqual(after.item?.status, operation == "confirm" ? "active" : "disabled")
        if operation == "confirm" { XCTAssertEqual(Array((after.item?.command.text ?? "").utf8), Array(f.edited_text.utf8)) }
        XCTAssertFalse(after.candidate_files.isEmpty); XCTAssertTrue(after.other_item_unchanged)
        XCTAssertEqual(after.input_sha256?.count, 64)
        try audit("candidate-original-" + language + "-max", target: app.staticTexts["memoryCandidate.historicalNotice"])
        if account {
            app.terminate(); app.launch(); XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 30)); signIn(f, language)
            tap("memory.accountDeletion"); tap("account.cleanup.review")
            let consent = app.switches.matching(identifier: "account.cleanup.consent")
            reveal(consent.element, centered: true); XCTAssertEqual(consent.count, 1)
            if consent.element.value as? String != "1" { consent.element.coordinate(withNormalizedOffset: .init(dx: 0.9, dy: 0.5)).tap() }
            XCTAssertEqual(consent.element.value as? String, "1")
            tap("account.cleanup.confirm"); text("account.cleanup.access", contains: "stopped")
            tap("account.cleanup.cleanDevice"); text("account.cleanup.native", contains: "clear")
            tap("account.cleanup.read"); text("account.cleanup.areas", contains: "31 of 31")
            let cleared = try await proof()
            XCTAssertTrue(cleared.candidate_files.isEmpty); XCTAssertTrue(cleared.memory_files.isEmpty)
            XCTAssertEqual(cleared.action_count, 1); XCTAssertEqual(cleared.action_id, actionID)
            XCTAssertEqual(cleared.input_sha256, after.input_sha256); XCTAssertTrue(cleared.other_item_unchanged)
            XCTAssertTrue([401, 403].contains(cleared.item_http_status))
            tap("account.cleanup.readDevice"); text("account.cleanup.deviceReceipt", contains: "Acknowledged for this device")
            tap("account.cleanup.finalizeControls"); text("account.cleanup.controls", contains: "removed and verified")
        }
    }
    func testConfirmCandidateEnglish() async throws { try await verify("en") }
    func testConfirmCandidateChinese() async throws { try await verify("zh-Hans") }
    func testRejectCandidateEnglish() async throws { try await verify("en", operation: "reject") }
    func testUnknownCandidateReopensChinese() async throws { try await verify("zh-Hans", reopen: true) }
    func testAccountClearsCandidateFamilyEnglish() async throws { try await verify("en", account: true) }
    func testFreshCurrentCandidateEnglish() async throws { try await verify("en", current: true) }
}
