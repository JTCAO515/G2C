import XCTest
import Foundation

/// Actual signed local producers only; no injected Memory records or UI model.
@MainActor final class DevelopmentTypedMemoryUITests: XCTestCase {
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private var chinese = false
    private func localized(_ english: String,_ zh: String) -> String {chinese ? zh : english}
    private struct Fixture: Decodable {
        let endpoint: String;let memory_endpoint: String;let accounts: [String:String];let subjects: [String:String]
        let travel_ids: [String];let travel_profile: String;let memory_profile: String
    }
    private func reveal(_ element: XCUIElement,id: String,fixed: Bool = false) {
        for _ in 0..<40 {
            var top = app.navigationBars.firstMatch.exists ? app.navigationBars.firstMatch.frame.maxY : app.frame.minY + 60
            var bottom = app.tabBars.firstMatch.exists ? app.tabBars.firstMatch.frame.minY : app.frame.maxY - 20
            let header = app.otherElements.matching(identifier:"assistant.header").firstMatch
            let composer = app.otherElements.matching(identifier:"assistant.composer").firstMatch
            if !fixed && !["assistant.draft","assistant.send","assistant.intent"].contains(id) && header.exists && composer.exists {
                top = max(top,header.frame.maxY + 8);bottom = min(bottom,composer.frame.minY)
            }
            let frame = element.exists ? element.frame : .zero
            if element.exists && element.isHittable && (fixed || frame.midY > top && frame.midY < bottom) {return}
            if fixed {_ = element.waitForExistence(timeout:1);continue}
            let down = frame != .zero && frame.midY <= top
            let start = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width * 0.85,dy:(down ? top + 20 : bottom - 20)))
            let end = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width * 0.85,dy:(down ? bottom - 20 : top + 20)))
            start.press(forDuration:0.05,thenDragTo:end)
        }
        let image = XCTAttachment(screenshot:app.screenshot());image.name = "not-visible-" + id;image.lifetime = .keepAlways;add(image)
        XCTAssertTrue(element.exists && element.isHittable,"Expected visible control: " + id)
    }
    private func tap(_ id: String) {
        let id = chinese ? (["Memory":"记忆","Assistant":"助手","Trips":"行程","Done":"完成"][id] ?? id) : id
        let target: XCUIElement
        if ["Memory","Assistant","Trips","记忆","助手","行程"].contains(id) { target = app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if id == "assistant.panel.done" { target = app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else { target = app.buttons.matching(identifier:id).firstMatch }
        let fixed = ["Memory","Assistant","Trips","记忆","助手","行程","assistant.panel.done"].contains(id)
        reveal(target,id:id,fixed:fixed)
        XCTAssertTrue(target.waitForExistence(timeout:10),id);XCTAssertTrue(target.isHittable,id)
        let enabled = XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:20),.completed,id);target.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
    }
    private func input(_ id: String,_ text: String) {
        // At maximum text size the next Form row can sit below the keyboard.
        // Close the previous editor before scrolling to that concrete field.
        dismissKeyboard()
        let view = app.textViews.matching(identifier:id).firstMatch
        let field = view.exists ? view : app.textFields.matching(identifier:id).firstMatch
        XCTAssertTrue(field.waitForExistence(timeout:15),id)
        reveal(field,id:id)
        XCTAssertTrue(field.isHittable,id);field.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout:10),"Expected keyboard focus for " + id)
        field.typeText(text)
        XCTAssertEqual(Array((field.value as? String ?? "").utf8),Array(text.utf8))
    }
    private func text(_ id: String,contains expected: String) {
        let label = app.staticTexts.matching(identifier:id).firstMatch
        // Form sections are lazy, including the original-result footer. Read
        // actual visible content rather than relying on an offscreen snapshot.
        reveal(label,id:id)
        XCTAssertTrue(label.waitForExistence(timeout:15),id)
        let value = XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",expected),object:label)
        let result = XCTWaiter.wait(for:[value],timeout:30)
        if result != .completed {
            let image = XCTAttachment(screenshot:app.screenshot());image.name = "failed-" + id;image.lifetime = .keepAlways;add(image)
        }
        XCTAssertEqual(result,.completed,id + " actual=" + label.label)
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
        dismissKeyboard()
        tap("memory2.manual.review")
        text("memory2.review.text",contains:value)
        tap("memory2.manual.confirm");text("memory2.save.status",contains:localized("Saved.","已保存"))
        back()
    }
    private func completedMessages(_ count: Int,expected: String = "Travel A quiet room / 本次A安静房间") async throws {
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(URL(string:control + "/wait-completed?count=" + String(count))))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        let value = try XCTUnwrap(JSONSerialization.jsonObject(with:data) as? [String:Any])
        XCTAssertEqual(value["model_calls"] as? Int,count)
        tap("run.snapshot.read")
        text("run.display.status",contains:localized("Completed","已完成"))
        text("run.display.text",contains:expected)
    }
    private func openChat(_ id: String) {
        tap("assistant.serverHistory");tap("history.loadConversations");tap("history.conversation." + id);tap("assistant.panel.done")
    }
    private func chooseTravel(_ id: String) {
        tap("assistant.travelContext");tap("travel.selection." + id);text("travel.selection.status",contains:id);tap("assistant.panel.done")
    }
    private func ask(_ prompt: String,count: Int,expected: String) async throws {
        input("assistant.draft",prompt)
        dismissKeyboard()
        tap("assistant.send");try await completedMessages(count,expected:expected)
    }
    private func launch(_ fixture: Fixture,restore: Bool) throws {
        app?.terminate();app = XCUIApplication(bundleIdentifier:"space.go2china.typed-memory.acceptance")
        app.launchArguments = ["-cj.ui.language.v1",chinese ? "zh-Hans" : "en"]
        if chinese {app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"]}
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1",
            "G2C_DEV_API_BASE_URL":fixture.endpoint,"G2C_DEV_ACCOUNTS":restore ? "{}" : String(data:try JSONEncoder().encode(fixture.accounts),encoding:.utf8)!,
            "G2C_DEV_TRAVEL_PROFILE":fixture.travel_profile,"G2C_DEV_TYPED_MEMORY_PROFILE":fixture.memory_profile,
            "G2C_DEV_TYPED_MEMORY_URL":fixture.memory_endpoint]
        app.launch();tap("Memory");tap("memory.account")
        if restore {tap("account.development.restore")}
        else {tap("account.development.signout");tap("account.development.signin.A")}
        text("account.development.status",contains:fixture.subjects["A"]!)
        let ready = app.buttons.matching(identifier:"memory2.items.open").firstMatch
        for _ in 0..<12 {
            tap("Memory")
            if app.staticTexts.matching(identifier:"account.development.status").firstMatch.exists {back()}
            if ready.exists {break};_ = ready.waitForExistence(timeout:1)
        }
        XCTAssertTrue(ready.waitForExistence(timeout:15))
    }
    private func dismissKeyboard() {
        if app.toolbars.buttons.matching(identifier:localized("Done","完成")).firstMatch.exists {tap("Done")}
    }
    func testChineseLargeSaveReadAndRecall() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600;chinese = true
        let fixture = try await prepare();defer {app?.terminate()}
        try launch(fixture,restore:false)
        save("中文长期偏好 / 长期 e\u{301}",scope:"Long term / 长期")
        tap("Assistant");chooseTravel(fixture.travel_ids[0]);tap("Memory")
        let value = "中文本次偏好 / 安静房间 e\u{301}"
        save(value,scope:"Selected travel / 所选旅行")
        tap("memory2.items.open");tap("memory2.items.read")
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(URL(string:control + "/items")))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        let ids = try JSONDecoder().decode([String:String].self,from:data)
        tap("memory2.item." + (try XCTUnwrap(ids["travel"])));tap("memory2.detail.read")
        text("memory2.detail.text",contains:value);text("memory2.detail.scope",contains:fixture.travel_ids[0])
        var issues = 0;continueAfterFailure = true
        try app.performAccessibilityAudit(for:.all) {issue in issues += 1;print("TYPED_MEMORY_ZH_LARGE",issue.detailedDescription,issue.element?.label ?? "unavailable",issue.element?.frame ?? .zero);return false}
        continueAfterFailure = false;XCTAssertEqual(issues,0)
        tap("Assistant");openChat("typed-chat-1");try await ask("请按当前旅行偏好回答",count:1,expected:value)
    }
    func testEnglishSaveReadAndOwnedTravel() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600
        let fixture = try await prepare()
        defer {app.terminate()}
        try launch(fixture,restore:false)
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
        try app.performAccessibilityAudit(for:.all) {issue in
            issues += 1;print("TYPED_MEMORY_DETAIL",issue.detailedDescription,issue.element?.label ?? "unavailable",issue.element?.frame ?? .zero);return false
        }
        continueAfterFailure = false;XCTAssertEqual(issues,0)
        tap("Assistant");openChat("typed-chat-1")
        try await ask("Recall current preferences from persisted memory",count:1,expected:"Travel A quiet room / 本次A安静房间")
        // Edit through the actual App/API, then prove the following turn reads
        // the new source version rather than the previous chat answer.
        let updated = "Travel A updated value / A当前新值"
        tap("Memory");tap("memory2.detail.read");input("memory2.edit.text",updated)
        if app.toolbars.buttons.matching(identifier:"Done").firstMatch.exists {tap("Done")}
        tap("memory2.manage.review.edit");text("memory2.manage.review.after",contains:updated);tap("memory2.manage.confirm")
        text("memory2.manage.status",contains:"Original receipt verified")
        tap("Assistant");try await ask("Use the current preference in the next turn",count:2,expected:updated)
        openChat("typed-chat-2");try await ask("Use persisted preferences in this new chat",count:3,expected:updated)
        try launch(fixture,restore:true)
        tap("Assistant");chooseTravel(fixture.travel_ids[0]);openChat("typed-chat-3")
        try await ask("Use current memory after restarting the App",count:4,expected:updated)
        chooseTravel(fixture.travel_ids[1])
        try await ask("Use only this other travel and long-term memory",count:5,expected:"Typed long-term tea / 新长期 e\u{301}")
        // The reopened client must query original save/lifecycle receipts before
        // a fresh save; navigating away does not erase verified completions.
        tap("Memory");tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let (originalData,originalResponse) = try await URLSession.shared.data(from:XCTUnwrap(URL(string:control + "/originals")))
        XCTAssertEqual((originalResponse as? HTTPURLResponse)?.statusCode,200)
        let originals = try JSONDecoder().decode([String:[String]].self,from:originalData)
        for original in try XCTUnwrap(originals["saves"]) {tap("memory2.original.query." + original);text("memory2.save.status",contains:"Saved.")}
        for original in try XCTUnwrap(originals["management"]) {tap("memory2.action.query." + original);text("memory2.manage.status",contains:"Original receipt verified")}
        back()
        save("Travel B separate value / B独立值",scope:"Selected travel / 所选旅行")
        tap("Assistant");try await ask("Use this travel's own updated preference",count:6,expected:"Travel B separate value / B独立值")
    }
}
