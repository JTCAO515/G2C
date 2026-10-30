import XCTest
import Foundation

@MainActor final class DevelopmentMemoryLifecycleUITests: XCTestCase {
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    struct Item: Decodable {
        struct Command: Decodable { let item_id: String; let text: String; let kind: String; let slot: String; let source_id: String; let source_version: Int }
        let command: Command; let version: Int; let status: String
    }
    struct Fixture: Decodable {
        let endpoint: String; let management_endpoint: String; let accounts: [String:String]; let subjects: [String:String]
        let profile: String; let case_id: String; let initial: [Item]
    }
    func call(_ path: String, _ values: [String:String]) async throws -> Data {
        var url = URLComponents(string:control+path)!;url.queryItems = values.map { URLQueryItem(name:$0.key,value:$0.value) }
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200);return data
    }
    func tap(_ id: String) {
        let target = app.buttons.matching(identifier:id).firstMatch
        for _ in 0..<60 {
            if target.exists && target.isHittable { break }
            if target.exists && target.frame.maxY < app.navigationBars.firstMatch.frame.maxY { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(target.waitForExistence(timeout:10),id);XCTAssertTrue(target.isHittable,id)
        let enabled = XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:15),.completed,id)
        target.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
    }
    func back() { app.navigationBars.buttons.firstMatch.tap() }
    func capture(_ name: String) { let a=XCTAttachment(screenshot:app.screenshot());a.name=name;a.lifetime = .keepAlways;add(a) }
    func audit(_ name: String) throws {
        var issues=0;continueAfterFailure=true;defer { continueAfterFailure=false }
        try app.performAccessibilityAudit(for:.all) { issue in issues += 1;print(name,issue.detailedDescription,issue.element?.label ?? "unavailable",issue.element?.frame ?? .zero);return false }
        continueAfterFailure=false;XCTAssertEqual(issues,0)
    }
    func launch(_ f: Fixture, language: String, large: Bool) throws {
        app?.terminate();app=XCUIApplication(bundleIdentifier:"space.go2china.memory-lifecycle.acceptance")
        app.launchArguments=["-cj.ui.language.v1",language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment=["G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,"G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,"G2C_DEV_MEMORY_PROFILE":f.profile,"G2C_DEV_MEMORY_MANAGEMENT_URL":f.management_endpoint]
        app.launch();tap(language=="en" ? "Memory":"记忆");tap("memory.account");tap("account.development.signout");tap("account.development.signin.A")
        let signed=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",f.subjects["A"]!),object:app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[signed],timeout:20),.completed);back()
    }
    func list(_ language: String) {
        tap(language=="en" ? "Load groups":"读取分组");tap("memory.group.0");tap(language=="en" ? "Load from start":"从头读取")
    }
    func open(_ id: String) {
        let row=app.buttons["memory.item."+id]
        for _ in 0..<60 {
            if row.exists && row.isHittable && row.frame.midY>app.navigationBars.firstMatch.frame.maxY && row.frame.midY<app.tabBars.firstMatch.frame.minY { break }
            if row.exists && row.frame.midY<=app.navigationBars.firstMatch.frame.maxY { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(row.waitForExistence(timeout:10));XCTAssertTrue(row.isHittable)
        row.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap();tap("memory.detail.refresh")
        XCTAssertTrue(app.staticTexts["memory.detail.text"].waitForExistence(timeout:15))
    }
    func status(_ expected: String) {
        let target=app.staticTexts["memory.manage.status"]
        let matched=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",expected),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[matched],timeout:30),.completed,target.exists ? target.label:"status missing")
    }
    func edit(_ text: String, language: String) {
        tap("memory.manage.edit")
        let field=app.textViews["memory.manage.text"]
        XCTAssertTrue(field.waitForExistence(timeout:10))
        for _ in 0..<30 { if field.isHittable { break };app.swipeUp() }
        XCTAssertTrue(field.isHittable);field.tap();XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout:5))
        let old=field.value as? String ?? ""
        field.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:old.count))
        field.typeText(text);XCTAssertEqual(Array((field.value as? String ?? "").utf8),Array(text.utf8))
        tap("memory.manage.keyboard.done");tap("memory.manage.saveEdit");tap(language=="en" ? "Confirm edited text":"确认编辑内容")
        status(language=="en" ? "Original action confirmed":"原操作已确认")
    }
    func action(_ id: String, _ confirm: String, language: String) {
        tap(id);tap(confirm);status(language=="en" ? "Original action confirmed":"原操作已确认")
    }
    @discardableResult func refreshed(_ f: Fixture, _ id: String, language: String) async throws -> Item {
        let current=try JSONDecoder().decode(Item.self,from:await call("/snapshot",["case":f.case_id,"item_id":id]))
        tap("memory.detail.refresh")
        let content=app.staticTexts["memory.detail.text"]
        let ready=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label == %@",current.command.text),object:content)
        XCTAssertEqual(XCTWaiter.wait(for:[ready],timeout:15),.completed)
        XCTAssertTrue(app.staticTexts[(language=="en" ? "Version, ":"版本, ")+String(current.version)].exists)
        XCTAssertTrue(app.staticTexts[(language=="en" ? "Source version, ":"来源版本, ")+String(current.command.source_version)].exists)
        XCTAssertTrue(app.staticTexts[(language=="en" ? "Source, ":"来源, ")+current.command.source_id].exists)
        return current
    }
    func success(language: String, large: Bool) async throws {
        continueAfterFailure=false
        let name=large ? "testChineseLarge":"testEnglish"
        let f=try JSONDecoder().decode(Fixture.self,from:await call("/prepare",["case":name]))
        defer { app?.terminate() };try launch(f,language:language,large:large);list(language)
        let fact=try XCTUnwrap(f.initial.first { $0.command.kind=="fact" })
        for original in f.initial {
            open(original.command.item_id)
            if !large || original.command.kind=="fact" {
                let input="Updated "+original.command.kind+" / 合成编辑 e\u{301} retained"
                edit(input,language:language)
                let current=try await refreshed(f,original.command.item_id,language:language)
                XCTAssertEqual(Array(current.command.text.utf8),Array(input.utf8));XCTAssertEqual(current.status,"active")
                XCTAssertNotEqual(current.command.source_id,original.command.source_id)
            }
            capture("current-source-"+original.command.kind+"-"+language);try audit("MEMORY_LIFECYCLE_"+language)
            back()
        }
        if !large {
            open(fact.command.item_id);action("memory.manage.pause","Confirm pause",language:language)
            var current=try await refreshed(f,fact.command.item_id,language:language);XCTAssertEqual(current.status,"disabled")
            edit("Edited while paused / 暂停期间编辑",language:language)
            current=try await refreshed(f,fact.command.item_id,language:language);XCTAssertEqual(current.status,"disabled")
            action("memory.manage.resume","Confirm resume",language:language)
            current=try await refreshed(f,fact.command.item_id,language:language);XCTAssertEqual(current.status,"active");back()
            let preference=try XCTUnwrap(f.initial.first { $0.command.kind=="preference" });open(preference.command.item_id)
            action("memory.manage.stopUse","Confirm stop using",language:language)
            current=try await refreshed(f,preference.command.item_id,language:language);XCTAssertEqual(current.status,"withdrawn")
            capture("stopped-with-history-retained");try audit("MEMORY_WITHDRAWN");back()
        }
        _ = try await call("/verify",["case":f.case_id])
    }
    func testEnglish() async throws { try await success(language:"en",large:false) }
    func testChineseLarge() async throws { try await success(language:"zh-Hans",large:true) }
}
