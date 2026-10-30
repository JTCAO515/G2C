import XCTest
import Foundation

/// Actual signed local producers only; no injected Memory records or UI model.
@MainActor final class DevelopmentTypedMemoryUITests: XCTestCase {
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private struct Fixture: Decodable {
        let endpoint: String;let memory_endpoint: String;let accounts: [String:String];let subjects: [String:String]
        let travel_ids: [String];let travel_profile: String;let memory_profile: String
    }
    private func tap(_ id: String) {
        let target: XCUIElement
        if ["Memory","Assistant","Trips"].contains(id) { target = app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if id == "assistant.panel.done" { target = app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else { target = app.buttons.matching(identifier:id).firstMatch }
        let fixed = ["Memory","Assistant","Trips","assistant.panel.done"].contains(id)
        for _ in 0..<30 {
            if target.exists && target.isHittable { break }
            if fixed { _ = target.waitForExistence(timeout:1) }
            else { app.swipeUp() }
        }
        XCTAssertTrue(target.waitForExistence(timeout:10),id);XCTAssertTrue(target.isHittable,id)
        let enabled = XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:20),.completed,id);target.tap()
    }
    private func input(_ id: String,_ text: String) {
        let view = app.textViews.matching(identifier:id).firstMatch
        let field = view.exists ? view : app.textFields.matching(identifier:id).firstMatch
        XCTAssertTrue(field.waitForExistence(timeout:15),id)
        for _ in 0..<20 { if field.isHittable { break };app.swipeUp() }
        XCTAssertTrue(field.isHittable,id);field.tap();field.typeText(text)
        XCTAssertEqual(Array((field.value as? String ?? "").utf8),Array(text.utf8))
    }
    private func text(_ id: String,contains expected: String) {
        let label = app.staticTexts.matching(identifier:id).firstMatch
        XCTAssertTrue(label.waitForExistence(timeout:15),id)
        let value = XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",expected),object:label)
        XCTAssertEqual(XCTWaiter.wait(for:[value],timeout:30),.completed,id + " actual=" + label.label)
    }
    private func back() {
        let target = app.navigationBars.firstMatch.buttons.firstMatch
        XCTAssertTrue(target.waitForExistence(timeout:10));XCTAssertTrue(target.isHittable);target.tap()
    }
    private func prepare() async throws -> Fixture {
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(URL(string:control + "/prepare")))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        return try JSONDecoder().decode(Fixture.self,from:data)
    }
    private func save(_ value: String,scope: String) {
        tap("memory.add");tap("memory2.manual.option")
        tap("self · preference · " + scope)
        input("memory2.manual.text",value);input("memory2.manual.time","time unknown / 时间不详")
        if app.toolbars.buttons.matching(identifier:"Done").firstMatch.exists { tap("Done") }
        tap("memory2.manual.review")
        text("memory2.review.text",contains:value)
        tap("memory2.manual.confirm");text("memory2.save.status",contains:"Saved.")
        back()
    }
    func testEnglishSaveReadAndOwnedTravel() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600
        let fixture = try await prepare()
        app = XCUIApplication(bundleIdentifier:"space.go2china.typed-memory.acceptance")
        defer {app.terminate()}
        app.launchArguments = ["-cj.ui.language.v1","en"]
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1",
            "G2C_DEV_API_BASE_URL":fixture.endpoint,"G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(fixture.accounts),encoding:.utf8)!,
            "G2C_DEV_TRAVEL_PROFILE":fixture.travel_profile,"G2C_DEV_TYPED_MEMORY_PROFILE":fixture.memory_profile,
            "G2C_DEV_TYPED_MEMORY_URL":fixture.memory_endpoint]
        app.launch();tap("Memory");tap("memory.account");tap("account.development.signout");tap("account.development.signin.A")
        text("account.development.status",contains:fixture.subjects["A"]!)
        let ready = app.buttons.matching(identifier:"memory2.items.open").firstMatch
        for _ in 0..<12 {
            tap("Memory")
            if app.staticTexts.matching(identifier:"account.development.status").firstMatch.exists {back()}
            if ready.exists {break};_ = ready.waitForExistence(timeout:1)
        }
        XCTAssertTrue(ready.waitForExistence(timeout:15))
        save("Typed long-term tea / 新长期 e\u{301}",scope:"Long term / 长期")
        tap("Assistant");tap("assistant.travelContext");tap("travel.selection." + fixture.travel_ids[0])
        text("travel.selection.status",contains:fixture.travel_ids[0]);tap("assistant.panel.done");tap("Memory")
        save("Travel A quiet room / 本次A安静房间",scope:"Selected travel / 所选旅行")
        tap("memory2.items.open");tap("memory2.items.read")
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(URL(string:control + "/items")))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        let ids = try JSONDecoder().decode([String:String].self,from:data)
        let id = try XCTUnwrap(ids["travel"])
        tap("memory2.item." + id);tap("memory2.detail.read")
        text("memory2.detail.text",contains:"Travel A quiet room / 本次A安静房间")
        text("memory2.detail.scope",contains:fixture.travel_ids[0]);text("memory2.detail.status",contains:"Active")
        let image = XCTAttachment(screenshot:app.screenshot());image.name = "typed-memory-real-detail";image.lifetime = .keepAlways;add(image)
        var issues = 0;continueAfterFailure = true
        try app.performAccessibilityAudit(for:.all) {issue in issues += 1;print("TYPED_MEMORY_DETAIL",issue.detailedDescription);return false}
        continueAfterFailure = false;XCTAssertEqual(issues,0)
    }
}
