import XCTest
import Foundation

/// Normal App erasure acceptance. The control host supplies local account/config
/// and observes actual API replies/files; it never injects a protected Memory
/// read, deletion action/operation, receipt or physical success into the App.
@MainActor final class MemoryErasureUITests: XCTestCase {
    let control = "__CONTROL_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable {
        let bundle: String
        let launch: [String: String]
        let subjects: [String: String]
        let option_label: String
        let other_option_label: String
        let text: String
        let other_text: String
        let occurred_at: String
    }
    struct Saved: Decodable { let item_id: String }
    struct LocalProof: Decodable {
        let item_journals: [String: String]
        let other_journals: [String: String]
        let erasure_originals: [String: String]
    }
    func call(_ path: String, query: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        if !query.isEmpty { url.queryItems = query.sorted(by: { $0.key < $1.key }).map { .init(name: $0.key, value: $0.value) } }
        let session = URLSession(configuration: .ephemeral); defer { session.invalidateAndCancel() }
        let (bytes, response) = try await session.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return bytes
    }
    func reveal(_ element: XCUIElement) {
        for _ in 0..<40 { if element.exists && element.isHittable { return }; app.swipeUp() }
        for _ in 0..<60 { if element.exists && element.isHittable { return }; app.swipeDown() }
        XCTFail("Exact erasure element is not visible")
    }
    func tap(_ id: String) {
        let query = app.buttons.matching(identifier: id), button = query.element
        reveal(button); XCTAssertEqual(query.count, 1, id)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 25), .completed, id)
        button.tap()
    }
    func text(_ id: String, contains value: String) {
        let element = app.staticTexts.matching(identifier: id).element
        reveal(element)
        let expected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", value), object: element)
        XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 30), .completed, id)
    }
    func enter(_ id: String, value: String) {
        let multiline = app.textViews.matching(identifier: id), single = app.textFields.matching(identifier: id)
        let query = multiline.element.exists ? multiline : single
        let field = query.element; reveal(field); XCTAssertEqual(query.count, 1)
        field.tap(); field.typeText(value)
        XCTAssertEqual(Array((field.value as? String ?? "").utf8), Array(value.utf8))
    }
    func audit(_ name: String, target: XCUIElement) throws {
        reveal(target); XCTAssertTrue(target.isHittable)
        continueAfterFailure = true
        var failures = 0
        try app.performAccessibilityAudit(for: .all) { issue in
            failures += 1; print(name, issue.detailedDescription, issue.element?.identifier ?? "unavailable"); return false
        }
        continueAfterFailure = false; XCTAssertEqual(failures, 0)
        let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = name; shot.lifetime = .keepAlways; add(shot)
    }
    func save(option: String, value: String, occurredAt: String, language: String) async throws -> Saved {
        tap("memory.add"); tap("memory2.manual.option"); tap(option)
        enter("memory2.manual.text", value: value)
        enter("memory2.manual.time", value: occurredAt)
        tap(language == "en" ? "Done" : "完成")
        tap("memory2.manual.review"); tap("memory2.manual.confirm")
        text("memory2.save.status", contains: language == "en" ? "Saved." : "已保存")
        let saved = try JSONDecoder().decode(Saved.self, from: await call("/observed-save"))
        XCTAssertFalse(saved.item_id.isEmpty)
        let back = app.navigationBars.buttons.matching(NSPredicate(format: "label == %@", language == "en" ? "Memory" : "记忆"))
        XCTAssertEqual(back.count, 1); back.element.tap()
        return saved
    }
    func verify(_ language: String) async throws {
        continueAfterFailure = false
        let fixture = try JSONDecoder().decode(Fixture.self, from: await call("/fixture"))
        _ = try await call("/size", query: ["value": "standard"])
        app = XCUIApplication(bundleIdentifier: fixture.bundle)
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = fixture.launch.merging(["OS_ACTIVITY_MODE": "disable"]) { _, required in required }
        app.launch(); defer { app.terminate() }
        XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 30))
        tap(language == "en" ? "Memory" : "记忆")
        tap("memory.account"); tap("account.development.signin.A")
        text("account.development.status", contains: try XCTUnwrap(fixture.subjects["A"]))
        let back = app.navigationBars.buttons.matching(NSPredicate(format: "label == %@", language == "en" ? "Memory" : "记忆"))
        XCTAssertEqual(back.count, 1); back.element.tap()
        let other = try await save(option: fixture.other_option_label, value: fixture.other_text, occurredAt: fixture.occurred_at, language: language)
        let saved = try await save(option: fixture.option_label, value: fixture.text, occurredAt: fixture.occurred_at, language: language)
        // This ID comes from the real successful App POST, never from launch env.
        XCTAssertNotEqual(saved.item_id, other.item_id)
        tap("memory2.items.open"); tap("memory2.items.read"); tap("memory2.item." + saved.item_id)
        tap("memory2.detail.read"); text("memory2.detail.text", contains: fixture.text)
        tap("memory2.erasure.review")
        _ = try await call("/size", query: ["value": "max"])
        text("memoryErasure.range", contains: language == "en" ? "not limited" : "不是只精准匹配")
        text("memoryErasure.retained", contains: language == "en" ? "retained" : "保留")
        let acknowledge = app.switches.matching(identifier: "memoryErasure.rangeAcknowledgement")
        reveal(acknowledge.element); XCTAssertEqual(acknowledge.count, 1)
        XCTAssertTrue(acknowledge.element.isEnabled); acknowledge.element.tap()
        try audit("erasure-review-" + language + "-max", target: app.buttons["memoryErasure.submit"])
        tap("memoryErasure.submit")
        text("memoryErasure.stopUse", contains: language == "en" ? "Stopped using" : "已停止使用")
        text("memoryErasure.onlineProgress", contains: language == "en" ? "Listed online content cleanup confirmed" : "所列线上内容已确认清理")
        let before = try JSONDecoder().decode(LocalProof.self, from: await call("/local-proof"))
        XCTAssertFalse(before.item_journals.isEmpty, "The App must have written actual target ciphertext before cleanup")
        XCTAssertFalse(before.other_journals.isEmpty, "A separate actual App journal must be preserved")
        XCTAssertFalse(before.erasure_originals.isEmpty, "The actual original deletion must already be durable")
        tap("memoryErasure.clearLocal")
        text("memoryErasure.localProgress", contains: language == "en" ? "physically cleared" : "物理清理")
        let after = try JSONDecoder().decode(LocalProof.self, from: await call("/local-proof"))
        XCTAssertTrue(after.item_journals.isEmpty)
        XCTAssertEqual(after.other_journals, before.other_journals)
        XCTAssertEqual(after.erasure_originals, before.erasure_originals)
        tap("memoryErasure.query")
        text("memoryErasure.stopUse", contains: language == "en" ? "Stopped using" : "已停止使用")
        try audit("erasure-complete-" + language + "-max", target: app.staticTexts["memoryErasure.localProgress"])
    }
    func testMemoryErasureEnglish() async throws { try await verify("en") }
    func testMemoryErasureChinese() async throws { try await verify("zh-Hans") }
}
