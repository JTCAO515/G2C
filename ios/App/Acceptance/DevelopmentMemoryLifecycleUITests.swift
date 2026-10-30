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
        let profile: String; let case_id: String; let initial: [Item]; let conversations: [String]
    }
    func call(_ path: String, _ values: [String:String]) async throws -> Data {
        var url = URLComponents(string:control+path)!;url.queryItems = values.map { URLQueryItem(name:$0.key,value:$0.value) }
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200);return data
    }
    func tap(_ id: String) {
        let target = app.buttons.matching(identifier:id).firstMatch
        let tab = app.tabBars.buttons.matching(identifier:id).firstMatch
        if tab.exists { XCTAssertTrue(tab.isHittable); tab.tap(); return }
        let nav = app.navigationBars.buttons.matching(identifier:id).firstMatch
        if nav.exists { XCTAssertTrue(nav.isHittable);XCTAssertTrue(nav.isEnabled);nav.tap();return }
        for _ in 0..<60 {
            let bar=app.navigationBars.firstMatch, tabs=app.tabBars.firstMatch
            let top=bar.exists ? bar.frame.maxY : app.frame.minY
            let bottom=tabs.exists ? tabs.frame.minY : app.frame.maxY
            if target.exists && target.isHittable && target.frame.midY>top && target.frame.midY<bottom { break }
            if target.exists && target.frame.midY<=top { app.swipeDown() } else { app.swipeUp() }
        }
        if !target.exists { XCTAssertTrue(target.waitForExistence(timeout:10),id) }
        XCTAssertTrue(target.exists,id);XCTAssertTrue(target.isHittable,id)
        if !target.isEnabled {
            let enabled = XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:target)
            XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:15),.completed,id)
        }
        XCTAssertTrue(target.isEnabled,id)
        target.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
    }
    func back() { app.navigationBars.buttons.firstMatch.tap() }
    func capture(_ name: String) { let a=XCTAttachment(screenshot:app.screenshot());a.name=name;a.lifetime = .keepAlways;add(a) }
    func audit(_ name: String) throws {
        var issues=0;continueAfterFailure=true;defer { continueAfterFailure=false }
        try app.performAccessibilityAudit(for:.all) { issue in issues += 1;print(name,issue.detailedDescription,issue.element?.label ?? "unavailable",issue.element?.frame ?? .zero);return false }
        continueAfterFailure=false;XCTAssertEqual(issues,0)
    }
    func launch(_ f: Fixture, language: String, large: Bool, restore: Bool = false) throws {
        app?.terminate();app=XCUIApplication(bundleIdentifier:"space.go2china.memory-lifecycle.acceptance")
        app.launchArguments=["-cj.ui.language.v1",language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment=["G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,"G2C_DEV_ACCOUNTS":restore ? "{}" : String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,"G2C_DEV_MEMORY_PROFILE":f.profile,"G2C_DEV_MEMORY_MANAGEMENT_URL":f.management_endpoint]
        app.launch();tap(language=="en" ? "Memory":"记忆");tap("memory.account")
        if restore { tap("account.development.restore") } else { tap("account.development.signout");tap("account.development.signin.A") }
        let signed=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",f.subjects["A"]!),object:app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[signed],timeout:20),.completed)
        // The verified root finishes assembling after the account label changes
        // and chooses Trips. Wait for its actual management capability in Memory.
        let ready=app.buttons["memory.manage.openOriginals"]
        for _ in 0..<10 {
            tap(language=="en" ? "Memory":"记忆")
            if app.staticTexts["account.development.status"].exists { back() }
            if ready.exists { break }
            _ = ready.waitForExistence(timeout:1)
        }
        XCTAssertTrue(ready.waitForExistence(timeout:10),app.debugDescription)
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
    func status(_ expected: String, id: String = "memory.manage.status") {
        let target=app.staticTexts[id]
        let matched=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",expected),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[matched],timeout:30),.completed,target.exists ? target.label:"status missing")
    }
    func enterEdit(_ text: String) {
        tap("memory.manage.edit")
        let field=app.textViews["memory.manage.text"]
        XCTAssertTrue(field.waitForExistence(timeout:10))
        for _ in 0..<30 { if field.isHittable { break };app.swipeUp() }
        XCTAssertTrue(field.isHittable);field.tap();XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout:5))
        field.press(forDuration:1)
        let names=NSPredicate(format:"label IN %@",["Select All","全选"])
        let menu=app.menuItems.matching(names).firstMatch
        let selectAll=menu.waitForExistence(timeout:2) ? menu : app.buttons.matching(names).firstMatch
        XCTAssertTrue(selectAll.waitForExistence(timeout:5));selectAll.tap()
        field.typeText(text);XCTAssertEqual(Array((field.value as? String ?? "").utf8),Array(text.utf8))
        tap("memory.manage.keyboard.done")
    }
    func submitEdit(language: String) { tap("memory.manage.saveEdit");tap(language=="en" ? "Confirm edited text":"确认编辑内容") }
    func edit(_ text: String, language: String) {
        enterEdit(text);submitEdit(language:language);status(language=="en" ? "Original action confirmed":"原操作已确认")
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
    struct Original: Decodable { let action_id: String; let sha256: String }
    func fixture(_ caseID: String) async throws -> Fixture {
        continueAfterFailure=false
        return try JSONDecoder().decode(Fixture.self,from:await call("/prepare",["case":caseID]))
    }
    func recover(_ original: Original, input: String, expected: String) {
        tap("memory.manage.openOriginals");tap("memory.manage.loadOriginals")
        let text=app.staticTexts["memory.manage.recoveredText"]
        XCTAssertTrue(text.waitForExistence(timeout:10));XCTAssertEqual(Array(text.label.utf8),Array(input.utf8))
        tap("memory.manage.recoveryQuery."+original.action_id)
        status(expected,id:"memory.manage.recoveryStatus."+original.action_id)
        XCTAssertTrue(app.staticTexts["memory.manage.recoveryID"].exists)
    }
    func testUnknownReopen() async throws {
        let f=try await fixture("testUnknownReopen");defer { app?.terminate() };try launch(f,language:"en",large:false);list("en")
        let fact=try XCTUnwrap(f.initial.first { $0.command.kind=="fact" });open(fact.command.item_id)
        let input="Unknown ACK original / 回执未知 e\u{301} retained"
        enterEdit(input);submitEdit(language:"en");status("Result unknown")
        XCTAssertEqual(app.staticTexts["memory.manage.originalText"].label,input)
        let original=try JSONDecoder().decode(Original.self,from:await call("/original",["case":f.case_id]))
        capture("actual-commit-ack-lost");try launch(f,language:"en",large:false,restore:true)
        recover(original,input:input,expected:"Original action confirmed")
        capture("original-query-after-reopen");try audit("MEMORY_EDIT_UNKNOWN_RECOVERED")
        _ = try await call("/verify",["case":f.case_id])
    }
    func testConflictReopen() async throws {
        let f=try await fixture("testConflictReopen");defer { app?.terminate() };try launch(f,language:"zh-Hans",large:true);list("zh-Hans")
        let fact=try XCTUnwrap(f.initial.first { $0.command.kind=="fact" });open(fact.command.item_id)
        let originalInput="保留冲突输入 / Retain exact conflict input e\u{301}"
        enterEdit(originalInput)
        _ = try await call("/concurrent-edit",["case":f.case_id,"item_id":fact.command.item_id])
        submitEdit(language:"zh-Hans");status("原操作已明确失败")
        XCTAssertEqual(Array(app.staticTexts["memory.manage.originalText"].label.utf8),Array(originalInput.utf8))
        let original=try JSONDecoder().decode(Original.self,from:await call("/original",["case":f.case_id]))
        capture("actual-cas-conflict-input-retained");try audit("MEMORY_EDIT_CONFLICT")
        try launch(f,language:"zh-Hans",large:true,restore:true)
        recover(original,input:originalInput,expected:"原操作已明确失败");capture("durable-original-failure-after-reopen");back();list("zh-Hans");open(fact.command.item_id)
        edit("重新审阅后的新编辑 / Explicit fresh review",language:"zh-Hans")
        let current=try await refreshed(f,fact.command.item_id,language:"zh-Hans");XCTAssertEqual(current.version,3)
        _ = try await call("/verify",["case":f.case_id])
    }
    func testSwitchLate() async throws {
        let f=try await fixture("testSwitchLate");defer { app?.terminate() };try launch(f,language:"en",large:false);list("en")
        let fact=try XCTUnwrap(f.initial.first { $0.command.kind=="fact" });open(fact.command.item_id)
        enterEdit("Old account committed / 旧账号已提交");submitEdit(language:"en")
        _ = try await call("/wait-held",["case":f.case_id]);status("Submitting original action")
        back();back();tap("memory.account");tap("account.development.signin.B")
        let signed=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",f.subjects["B"]!),object:app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[signed],timeout:15),.completed)
        _ = try await call("/release",["case":f.case_id]);back();tap("Load groups")
        XCTAssertTrue(app.staticTexts["No memory groups"].waitForExistence(timeout:15))
        XCTAssertFalse(app.staticTexts["Old account committed / 旧账号已提交"].exists)
        capture("late-a-response-not-shown-to-b");_ = try await call("/verify",["case":f.case_id])
    }
    func selectConversation(_ id: String) {
        tap("Assistant");tap("assistant.serverHistory");tap("history.loadConversations");tap("history.conversation."+id);tap("assistant.panel.done")
    }
    func send(_ text: String) {
        let intent=app.switches["assistant.intent"]
        if intent.exists && intent.value as? String=="1" { intent.tap() }
        let field=app.textViews["assistant.draft"];XCTAssertTrue(field.waitForExistence(timeout:10));field.tap()
        if let old=field.value as? String,old != "Start chatting",!old.isEmpty { field.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:old.count)) }
        field.typeText(text);XCTAssertEqual(field.value as? String,text)
        if app.buttons["Done"].exists { tap("Done") }
        tap("assistant.send")
    }
    func waitRun(_ expected: String) { status(expected,id:"run.display.status") }
    func runTextContains(_ expected: String, present: Bool) {
        let text=app.staticTexts["run.display.text"]
        if present { XCTAssertTrue(text.waitForExistence(timeout:10));XCTAssertTrue(text.label.contains(expected)) }
        else { XCTAssertFalse(text.exists && text.label.contains(expected));let stream=app.staticTexts["run.stream.text"];XCTAssertFalse(stream.exists && stream.label.contains(expected)) }
    }
    func testRuntimeRecall() async throws {
        let f=try await fixture("testRuntimeRecall");defer { app?.terminate() };try launch(f,language:"en",large:false);list("en")
        let fact=try XCTUnwrap(f.initial.first { $0.command.kind=="fact" });open(fact.command.item_id)
        let current="Current approved memory / 当前已编辑有效值"
        edit(current,language:"en");_ = try await refreshed(f,fact.command.item_id,language:"en")
        selectConversation(f.conversations[0]);send("Synthetic current effective memory one");waitRun("Completed");runTextContains(current,present:true)
        _ = try await call("/hold-provider",["case":f.case_id]);send("Synthetic actual in-flight old memory")
        _ = try await call("/wait-provider",["case":f.case_id])
        tap("Memory");tap("memory.detail.refresh");action("memory.manage.pause","Confirm pause",language:"en")
        _ = try await refreshed(f,fact.command.item_id,language:"en")
        _ = try await call("/release-provider",["case":f.case_id]);tap("Assistant");waitRun("Context invalid");runTextContains(current,present:false);capture("actual-old-context-invalid")
        send("Synthetic same chat while paused");waitRun("Completed");runTextContains(current,present:false)
        tap("Memory");tap("memory.detail.refresh");action("memory.manage.resume","Confirm resume",language:"en");_ = try await refreshed(f,fact.command.item_id,language:"en")
        selectConversation(f.conversations[1]);send("Synthetic new chat after resume");waitRun("Completed");runTextContains(current,present:true)
        try launch(f,language:"en",large:false,restore:true);selectConversation(f.conversations[0]);send("Synthetic current state after App reopen");waitRun("Completed");runTextContains(current,present:true)
        capture("current-effective-values-after-reopen");_ = try await call("/verify",["case":f.case_id])
    }
    func testReleaseClosed() async throws {
        let f=try await fixture("testReleaseClosed");defer { app?.terminate() }
        app=XCUIApplication(bundleIdentifier:"space.go2china.memory-lifecycle.acceptance")
        app.launchArguments=["-cj.ui.language.v1","en"]
        app.launchEnvironment=["G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,"G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,"G2C_DEV_MEMORY_PROFILE":f.profile,"G2C_DEV_MEMORY_MANAGEMENT_URL":f.management_endpoint]
        app.launch();tap("Memory")
        XCTAssertFalse(app.buttons["account.development.signin.A"].exists)
        XCTAssertFalse(app.buttons["memory.manage.edit"].exists);XCTAssertFalse(app.buttons["memory.manage.pause"].exists)
        capture("release-management-remains-closed");_ = try await call("/verify",["case":f.case_id])
    }

}
