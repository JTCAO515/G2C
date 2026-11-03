import XCTest
import Foundation

@MainActor final class PreservedHistoryUITests: XCTestCase {
    let control = "__CONTROL_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable {
        let endpoint: String
        let accounts: [String: String]
        let subjects: [String: String]
        let conversation_id: String
        let message_id: String
        let text: String
        let answer: String
    }
    func call(_ path: String) async throws -> Data {
        let session = URLSession(configuration: .ephemeral); defer { session.invalidateAndCancel() }
        let (bytes, response) = try await session.data(from: XCTUnwrap(URL(string: control + path)))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200); return bytes
    }
    func reveal(_ element: XCUIElement) {
        for _ in 0..<40 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        for _ in 0..<60 {
            if element.exists && element.isHittable { return }
            app.swipeDown()
        }
        XCTFail("Exact history element is not visible")
    }
    func tap(_ id: String) {
        let query = app.buttons.matching(identifier: id)
        let button = query.element
        reveal(button); XCTAssertEqual(query.count, 1, id)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: button)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 20), .completed, id)
        button.tap()
    }
    func audit(_ name: String, target: XCUIElement) throws {
        reveal(target); XCTAssertTrue(target.isHittable)
        continueAfterFailure = true
        var count = 0
        try app.performAccessibilityAudit(for: .all) { issue in
            count += 1; print(name, issue.detailedDescription, issue.element?.identifier ?? "unavailable"); return false
        }
        continueAfterFailure = false; XCTAssertEqual(count, 0)
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
    func verify(_ language: String) async throws {
        continueAfterFailure = false
        let f = try JSONDecoder().decode(Fixture.self, from: await call("/fixture"))
        _ = try await call("/size?value=max")
        app = XCUIApplication(bundleIdentifier: "space.go2china.preserved-history.acceptance")
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable", "G2C_DEV_ACCOUNT_MODE":"1", "G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_ACCOUNTS":try XCTUnwrap(String(data: JSONEncoder().encode(f.accounts), encoding: .utf8))]
        app.launch(); defer { app.terminate() }
        XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 25))
        tap(language == "en" ? "Memory" : "记忆")
        tap("memory.account"); tap("account.development.signin.A")
        let account = app.staticTexts["account.development.status"]
        let signed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", f.subjects["A"]!), object: account)
        XCTAssertEqual(XCTWaiter.wait(for: [signed], timeout: 25), .completed)
        tap(language == "en" ? "Assistant" : "助手")
        tap("assistant.serverHistory"); tap("history.loadConversations")
        tap("history.conversation." + f.conversation_id)
        tap("history.loadMessages")
        let original = app.staticTexts["history.message." + f.message_id]
        reveal(original); XCTAssertEqual(original.label, f.text)
        let erased = app.staticTexts["history.source.erased." + f.message_id]
        reveal(erased)
        XCTAssertTrue(erased.label.contains(language == "en" ? "viewing only" : "仅供查看"))
        tap("history.answer.read." + f.message_id)
        let answer = app.staticTexts["history.answer.text." + f.message_id]
        reveal(answer); XCTAssertEqual(answer.label, f.answer)
        let readonly = app.staticTexts["history.answer.readonly." + f.message_id]
        reveal(readonly)
        XCTAssertTrue(readonly.label.contains(language == "en" ? "does not resend" : "不会重发"))
        try audit("preserved-formal-history-" + language + "-max", target: answer)
    }
    func testErasedHistoryEnglish() async throws { try await verify("en") }
    func testErasedHistoryChinese() async throws { try await verify("zh-Hans") }
}
