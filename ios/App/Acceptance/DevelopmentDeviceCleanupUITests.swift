import XCTest
import Foundation

@MainActor final class DevelopmentDeviceCleanupUITests: XCTestCase {
    let control = "__CONTROL_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable { let endpoint: String; let accounts: [String: String]; let subjects: [String: String]; let case_id: String }
    struct Operation: Decodable { let operation_id: String; let phase: String }
    struct Account: Decodable { let operations: [Operation]; let fences: Int; let feedback: Int }
    struct Proof: Decodable { let accounts: [String: Account]; let provider_calls: Int }
    @discardableResult func call(_ path: String, _ name: String, _ values: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        url.queryItems = values.merging(["case": name]) { _, n in n }.map { .init(name: $0.key, value: $0.value) }
        let config = URLSessionConfiguration.ephemeral; config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        let session = URLSession(configuration: config); defer { session.invalidateAndCancel() }
        let (bytes, response) = try await session.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, path)
        return bytes
    }
    func fixture(_ name: String) async throws -> Fixture { try JSONDecoder().decode(Fixture.self, from: await call("/fixture", name)) }
    func proof(_ name: String) async throws -> Proof { try JSONDecoder().decode(Proof.self, from: await call("/proof", name)) }
    func launch(_ f: Fixture, language: String = "en") throws {
        continueAfterFailure = false
        app?.terminate(); app = XCUIApplication(bundleIdentifier: "space.go2china.device-v3.acceptance")
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["OS_ACTIVITY_MODE": "disable", "G2C_DEV_ACCOUNT_MODE": "1",
            "G2C_DEV_API_BASE_URL": f.endpoint, "G2C_DEV_OFFLINE_TRIP": "last-sync-v1", "G2C_DEV_CLEANUP_PROFILE": "device-v3",
            "G2C_DEV_ACCOUNTS": try XCTUnwrap(String(data: JSONEncoder().encode(f.accounts), encoding: .utf8))]
        app.launch(); XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["g2c.dev.error"].exists)
    }
    func reveal(_ element: XCUIElement) {
        for attempt in 0..<45 {
            let bar = app.navigationBars.firstMatch
            let top = bar.exists ? bar.frame.maxY + 4 : app.frame.minY + 48
            let bottom = app.tabBars.element.exists && app.tabBars.element.isHittable ? app.tabBars.element.frame.minY - 4 : app.frame.maxY - 40
            let frame = element.exists ? element.frame : .zero
            print("CLEANUP_SCROLL", element.exists ? element.identifier : "not-materialized", frame, "bounds", top, bottom, "hittable", element.exists && element.isHittable)
            if element.exists && element.isHittable && frame.midY >= top && frame.midY <= bottom { return }
            let down = frame.isEmpty ? (attempt / 10) % 2 == 1 : frame.midY < top
            let middle = (top + bottom) / 2, step = min(100, (bottom - top) * 0.15)
            let x = app.frame.width * 0.85
            app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: x, dy: middle + (down ? -step : step)))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: x, dy: middle + (down ? step : -step))))
        }
        XCTFail("Exact element was not scroll reachable: " + (element.exists ? element.identifier : "not-materialized"))
    }
    func tap(_ id: String) {
        let query = app.buttons.matching(identifier: id), button = query.element
        let fixedControl = app.tabBars.buttons.matching(identifier: id).count == 1 || app.navigationBars.buttons.matching(identifier: id).count == 1
        if fixedControl { XCTAssertTrue(button.waitForExistence(timeout: 25), id) }
        else { reveal(button) }
        XCTAssertEqual(query.count, 1, id)
        XCTAssertTrue(button.isHittable, id)
        let wait = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [wait], timeout: 25), .completed, id)
        button.coordinate(withNormalizedOffset: .init(dx: 0.5, dy: 0.5)).tap()
    }
    func contains(_ id: String, _ expected: String) {
        let wait = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", expected), object: app.staticTexts[id])
        XCTAssertEqual(XCTWaiter.wait(for: [wait], timeout: 25), .completed, id)
    }
    func account(_ language: String = "en") {
        tap(language == "en" ? "Memory" : "记忆")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
    }
    func deletion(_ language: String = "en") {
        tap(language == "en" ? "Memory" : "记忆")
        // A current account page and the Memory root expose the same workflow.
        if app.buttons["account.deletion.open"].exists { tap("account.deletion.open") }
        else if !app.buttons["account.cleanup.read"].exists && !app.buttons["account.cleanup.review"].exists { tap("memory.accountDeletion") }
    }
    func consentAndConfirm() {
        let toggle = app.switches["account.cleanup.consent"]
        XCTAssertTrue(toggle.waitForExistence(timeout: 25)); reveal(toggle)
        if toggle.value as? String != "1" { toggle.tap() }
        tap("account.cleanup.confirm")
    }
    func audit(_ name: String, target: String) throws {
        let item = app.buttons[target].exists ? app.buttons[target] : app.staticTexts[target]
        XCTAssertTrue(item.waitForExistence(timeout: 20)); reveal(item)
        continueAfterFailure = true
        var count = 0
        try app.performAccessibilityAudit(for: .all) { issue in
            count += 1; print(name, issue.detailedDescription, issue.element?.label ?? "unavailable"); return false
        }
        continueAfterFailure = false; XCTAssertEqual(count, 0)
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    func seedDraft(_ text: String) {
        tap("Assistant"); tap("assistant.serverHistory"); tap("history.loadConversations"); tap("history.conversation.native-cleanup")
        tap("assistant.panel.done")
        let editor = app.textViews["assistant.draft"].exists ? app.textViews["assistant.draft"] : app.textFields["assistant.draft"]
        XCTAssertTrue(editor.waitForExistence(timeout: 20)); editor.tap(); editor.typeText(text)
        let keyboardDone = app.toolbars.buttons.matching(identifier: "Done")
        XCTAssertTrue(keyboardDone.element.waitForExistence(timeout: 5)); XCTAssertEqual(keyboardDone.count, 1)
        keyboardDone.element.tap()
    }
    func initial(_ f: Fixture, seedPrivateDraft: Bool = false) async throws -> String {
        try launch(f); account()
        if seedPrivateDraft {
            tap("account.development.signin.B"); contains("account.development.status", f.subjects["B"]!)
            seedDraft("另一账号保留的中文草稿。")
            account()
        }
        tap("account.development.signin.A"); contains("account.development.status", f.subjects["A"]!)
        if seedPrivateDraft {
            seedDraft("本机原始中文草稿，未发送。")
            account(); try await call("/native-files", f.case_id, ["stage": "before"])
        }
        deletion(); tap("account.cleanup.review")
        XCTAssertTrue(app.buttons["account.cleanup.confirm"].waitForExistence(timeout: 25))
        let p = try await proof(f.case_id); XCTAssertEqual(p.provider_calls, 2); XCTAssertEqual(p.accounts["A"]?.operations.count, 1)
        return try XCTUnwrap(p.accounts["A"]?.operations.first?.operation_id)
    }
    func testActualCommittedUnknownReopen() async throws {
        let name = "testActualCommittedUnknownReopen", f = try await fixture(name)
        _ = try await initial(f, seedPrivateDraft: true); defer { app?.terminate() }
        try audit("delete-account-en-max", target: "account.cleanup.confirm")
        try await call("/fault", name, ["kind": "confirmation"]); consentAndConfirm()
        contains("account.cleanup.unknown", "unknown")
        let committed = try await proof(name); XCTAssertEqual(committed.accounts["A"]?.fences, 1)
        try launch(f); deletion(); tap("account.cleanup.read"); contains("account.cleanup.access", "stopped")
        try await call("/fault", name, ["kind": "device-receipt"])
        tap("account.cleanup.cleanDevice"); contains("account.cleanup.native", "clear")
        contains("account.cleanup.unknown", "unknown")
        try await call("/native-files", name, ["stage": "after"])
        try launch(f, language: "zh-Hans"); deletion("zh-Hans"); tap("account.cleanup.readDevice")
        contains("account.cleanup.deviceReceipt", "已确认")
        try audit("delete-account-zh-max-original-device", target: "account.cleanup.readDevice")
        try await call("/validate", name)
        account("zh-Hans"); tap("account.development.signin.B"); contains("account.development.status", f.subjects["B"]!)
        deletion("zh-Hans"); XCTAssertTrue(app.buttons["account.cleanup.review"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["account.cleanup.native"].exists)
    }
    func testActualPreparationUnknown() async throws {
        let name = "testActualPreparationUnknown", f = try await fixture(name); defer { app?.terminate() }
        try launch(f); account(); tap("account.development.signin.A"); contains("account.development.status", f.subjects["A"]!)
        deletion(); try await call("/fault", name, ["kind": "preparation"]); tap("account.cleanup.review")
        contains("account.cleanup.unknown", "unknown")
        let prepared = try await proof(name)
        let original = try XCTUnwrap(prepared.accounts["A"]?.operations.first?.operation_id)
        try launch(f); account(); tap("account.development.restore"); contains("account.development.status", f.subjects["A"]!)
        deletion(); tap("account.cleanup.read"); XCTAssertTrue(app.buttons["account.cleanup.confirm"].waitForExistence(timeout: 25))
        let recovered = try await proof(name); XCTAssertEqual(recovered.accounts["A"]?.operations.first?.operation_id, original)
        try audit("delete-account-original-preparation-max", target: "account.cleanup.confirm")
        try await call("/validate", name)
    }
    func testActualFullInventoryBlocked() async throws {
        let name = "testActualFullInventoryBlocked", f = try await fixture(name)
        _ = try await initial(f); defer { app?.terminate() }
        consentAndConfirm(); contains("account.cleanup.access", "not been revoked")
        contains("account.cleanup.progress", "Blocked")
        XCTAssertFalse(app.buttons["account.cleanup.cleanDevice"].exists)
        try audit("delete-account-full-registry-blocked-max", target: "account.cleanup.read")
        try await call("/validate", name)
    }
}
