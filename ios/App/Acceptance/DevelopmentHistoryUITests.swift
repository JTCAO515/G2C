import XCTest
import Foundation

@MainActor final class DevelopmentHistoryUITests: XCTestCase {
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable { let endpoint: String; let accounts: [String: String]; let subjects: [String: String]; let case_id: String; let conversation: String; let second_conversation: String; let foreign_conversation: String; let profile: String; let prompt: String }
    struct Action: Decodable { let action_id: String; let sha256: String; let conversation: String; let operation: String; let source_version: Int64 }
    struct Consent: Decodable { let conversation: String; let enabled: Bool; let source_version: Int64 }
    struct Account: Decodable { let role: String; let actions: [Action]; let consents: [Consent]; let memory_items: Int; let jobs: Int }
    struct Proof: Decodable { let accounts: [String: Account]; let provider_calls: Int; let history_posts: Int }
    @discardableResult func call(_ path: String, _ caseID: String, _ values: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        url.queryItems = values.merging(["case": caseID]) { _, new in new }.map { .init(name: $0.key, value: $0.value) }
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, path); return data
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
        print("history tap", id, target.frame)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: target)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 20), .completed, id)
        // XCTest selected a cell-edge activation point for a partially exposed
        // multiline button. Use the resolved, fully visible control's center.
        target.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
    }
    func launch(_ f: Fixture, language: String = "en") throws {
        app?.terminate(); app = XCUIApplication(bundleIdentifier: "space.go2china.history.acceptance")
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable", "G2C_DEV_ACCOUNT_MODE":"1", "G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_MEMORY_HISTORY_PROFILE":"history-v1", "G2C_DEV_MEMORY_PROFILE":f.profile,
            "G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!]
        app.launch();XCTAssertTrue(app.tabBars.element.waitForExistence(timeout:15));XCTAssertFalse(app.staticTexts["g2c.dev.error"].exists)
    }
    func back() { let buttons=app.navigationBars.buttons;XCTAssertEqual(buttons.count,1);buttons.element.tap() }
    func account(_ language: String = "en") {
        tap(language == "en" ? "Memory" : "记忆")
        if !app.staticTexts["account.development.status"].exists {tap("memory.account")}
    }
    func signed(_ f: Fixture, _ key: String = "A") {
        let condition=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",f.subjects[key]!),object:app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[condition],timeout:25),.completed)
    }
    func login(_ f: Fixture, language: String = "en", restore: Bool = false) {
        account(language)
        if restore {tap("account.development.restore")}
        else {tap("account.development.signout");tap("account.development.signin.A")}
        signed(f)
    }
    func choose(_ id: String, language: String = "en") {
        tap(language == "en" ? "Assistant" : "助手");tap("assistant.serverHistory");tap("history.loadConversations")
        tap("history.conversation."+id);tap("assistant.panel.done")
    }
    func open(_ language: String = "en") {
        tap(language == "en" ? "Memory" : "记忆")
        if app.staticTexts["account.development.status"].exists {back()}
        tap("memory.historyConsent")
        XCTAssertTrue(app.staticTexts["historyConsent.status"].waitForExistence(timeout:20))
    }
    func current(_ enabled: Bool, version: Int64) {
        let value=app.staticTexts["historyConsent.version"]
        let condition=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label ENDSWITH %@",String(version)),object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[condition],timeout:25),.completed,value.exists ? value.label : "missing version")
        let toggle=app.switches["historyConsent.toggle"]
        XCTAssertTrue(toggle.exists);XCTAssertEqual(toggle.value as? String,enabled ? "1" : "0")
    }
    func change(_ enabled: Bool, version: Int64) {
        let toggle=app.switches["historyConsent.toggle"]
        for _ in 0..<15 {if toggle.exists && toggle.isHittable{break};app.swipeDown()}
        XCTAssertTrue(toggle.isHittable && toggle.isEnabled)
        toggle.switches.element.tap();current(enabled,version:version)
    }
    func capture(_ name: String) {let shot=XCTAttachment(screenshot:app.screenshot());shot.name=name;shot.lifetime = .keepAlways;add(shot)}
    func status(_ fragment: String) {
        let value=app.staticTexts["historyConsent.status"]
        let condition=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",fragment),object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[condition],timeout:25),.completed,value.exists ? value.label : "missing status")
    }
    func revealText(_ id: String) -> XCUIElement {
        let query=app.descendants(matching:.any).matching(identifier:id),target=query.element
        for attempt in 0..<45 {
            if target.exists && target.isHittable {break}
            let frame=target.exists ? target.frame : .zero
            let top=app.navigationBars.element.frame.maxY+8,bottom=app.tabBars.element.frame.minY-8
            let located = !frame.isEmpty && frame.minY.isFinite && frame.maxY.isFinite
            let down=located ? frame.midY<top : (attempt/8)%2 == 1
            let middle=(top+bottom)/2,step=min(110,(bottom-top)*0.15)
            let start=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? -step:step)))
            let end=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? step:-step)))
            start.press(forDuration:0.05,thenDragTo:end)
        }
        XCTAssertEqual(query.count,1,id);XCTAssertTrue(target.isHittable,id)
        return target
    }
    func audit(_ name: String) throws {
        let ids=["historyConsent.scope","historyConsent.conversation","historyConsent.read","historyConsent.status","historyConsent.stopExplanation","historyConsent.confirmationExplanation","historyConsent.loadPending"]
        for id in ids {
            let query=app.descendants(matching:.any).matching(identifier:id),target=query.element
            for attempt in 0..<45 {
                if target.exists && target.isHittable{break}
                let frame=target.exists ? target.frame : .zero
                let top=app.navigationBars.element.frame.maxY+8,bottom=app.tabBars.element.frame.minY-8
                let down=frame.isEmpty ? (attempt/8)%2 == 1 : frame.midY<top
                let middle=(top+bottom)/2,step=min(110,(bottom-top)*0.15)
                let start=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? -step:step)))
                let end=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? step:-step)))
                start.press(forDuration:0.05,thenDragTo:end)
            }
            XCTAssertEqual(query.count,1,id);XCTAssertTrue(target.isHittable,id);capture(name+"-"+id)
            continueAfterFailure=true;var issues=0
            try app.performAccessibilityAudit(for:.all){issue in issues += 1;print(name,id,issue.detailedDescription,issue.element?.label ?? "unavailable");return false}
            continueAfterFailure=false;XCTAssertEqual(issues,0)
        }
    }
    func saveOneMemory(_ language: String) {
        back();tap("memory.add");tap("memory.manual.scope");tap("self · food.spice · Long term / 长期")
        let text=app.textViews["memory.manual.text"];XCTAssertTrue(text.waitForExistence(timeout:8));text.tap();text.typeText("只保存这一条偏好，不授权全部历史")
        tap("memory.keyboard.done")
        let time=app.textFields["memory.manual.time"];XCTAssertTrue(time.exists);time.tap();time.typeText("日期不详")
        tap("memory.keyboard.done");tap("memory.manual.save")
        let saved=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",language=="en" ? "Saved." : "已保存"),object:app.staticTexts["memory.save.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[saved],timeout:25),.completed);back();tap("memory.historyConsent")
    }
    func sendContext(_ f: Fixture, language: String) {
        let draft=app.textViews["assistant.draft"]
        XCTAssertTrue(draft.waitForExistence(timeout:10));draft.coordinate(withNormalizedOffset:CGVector(dx:0.1,dy:0.2)).tap();draft.typeText(f.prompt)
        tap("assistant.send")
        let done=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",language=="en" ? "Completed" : "已完成"),object:app.staticTexts["run.display.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[done],timeout:40),.completed)
    }
    func basic(_ name: String, language: String) async throws {
        let f=try await prepare(name);defer{app?.terminate()}
        try launch(f,language:language);login(f,language:language);choose(f.conversation,language:language);sendContext(f,language:language);open(language)
        current(false,version:0)
        let empty=try await proof(f);XCTAssertEqual(empty.accounts["A"]?.actions.count,0)
        saveOneMemory(language);current(false,version:0)
        let manual=try await proof(f);XCTAssertEqual(manual.accounts["A"]?.memory_items,1);XCTAssertEqual(manual.accounts["A"]?.actions.count,0)
        change(true,version:1);change(false,version:2)
        let original=try await proof(f);XCTAssertEqual(original.accounts["A"]?.actions.count,2);XCTAssertEqual(original.accounts["A"]?.memory_items,1)
        back();choose(f.second_conversation,language:language);open(language);current(false,version:0)
        _=try await call("/size",f.case_id,["value":"accessibility-extra-extra-extra-large"])
        try audit("history-max-"+language)
        let last=try await proof(f);XCTAssertEqual(last.history_posts,original.history_posts);XCTAssertEqual(last.provider_calls,1)
        _=try await call("/validate",f.case_id)
    }
    func testHistoryEnglish() async throws {try await basic("testHistoryEnglish",language:"en")}
    func testHistoryChinese() async throws {try await basic("testHistoryChinese",language:"zh-Hans")}
    func testHistoryUnknownReopen() async throws {
        let f=try await prepare("testHistoryUnknownReopen");defer{app?.terminate()}
        try launch(f);login(f);choose(f.conversation);open();current(false,version:0)
        _=try await call("/fault",f.case_id,["kind":"drop"])
        let toggle=app.switches["historyConsent.toggle"];toggle.switches.element.tap();status("not confirmed")
        let before=try await proof(f),original=try XCTUnwrap(before.accounts["A"]?.actions.first)
        _=try await call("/other-change",f.case_id,["operation":"disable"])
        try launch(f,language:"zh-Hans");login(f,language:"zh-Hans",restore:true);choose(f.conversation,language:"zh-Hans");open("zh-Hans");current(false,version:2)
        XCTAssertFalse(app.switches["historyConsent.toggle"].isEnabled)
        tap("historyConsent.loadPending");tap("historyConsent.pending."+original.action_id);tap("historyConsent.query")
        current(false,version:2)
        XCTAssertTrue(revealText("historyConsent.historicalNotice").exists)
        let after=try await proof(f);XCTAssertEqual(after.history_posts,before.history_posts);XCTAssertTrue(after.accounts["A"]!.actions.contains{$0.sha256==original.sha256})
        try audit("history-original-historical-current-off");_=try await call("/validate",f.case_id)
    }
    func testHistoryConflict() async throws {
        let f=try await prepare("testHistoryConflict");defer{app?.terminate()}
        try launch(f);login(f);choose(f.conversation);open();current(false,version:0)
        _=try await call("/other-change",f.case_id,["operation":"enable"])
        app.switches["historyConsent.toggle"].switches.element.tap();status("source changed")
        XCTAssertFalse(app.switches["historyConsent.toggle"].exists)
        tap("historyConsent.read");current(true,version:1);change(false,version:2)
        let value=try await proof(f);XCTAssertEqual(value.history_posts,2)
        _=try await call("/validate",f.case_id)
    }
    func testHistoryLateSwitch() async throws {
        let f=try await prepare("testHistoryLateSwitch");defer{app?.terminate()}
        try launch(f);login(f);choose(f.conversation);open();current(false,version:0)
        _=try await call("/fault",f.case_id,["kind":"hold"])
        app.switches["historyConsent.toggle"].switches.element.tap();_=try await call("/wait-held",f.case_id)
        back();account();tap("account.development.signin.B");signed(f,"B")
        _=try await call("/release",f.case_id)
        choose(f.foreign_conversation);open();current(false,version:0)
        XCTAssertFalse(app.staticTexts["historyConsent.originalID"].exists)
        tap("historyConsent.loadPending");XCTAssertEqual(app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","historyConsent.pending.")).count,0)
        let value=try await proof(f);XCTAssertEqual(value.accounts["A"]?.actions.count,1);XCTAssertEqual(value.accounts["B"]?.actions.count,0)
        try audit("history-new-account-no-old-result");_=try await call("/validate",f.case_id)
    }
    func testHistoryReadUnavailable() async throws {
        let f=try await prepare("testHistoryReadUnavailable");defer{app?.terminate()}
        try launch(f);login(f);choose(f.conversation)
        _=try await call("/fault",f.case_id,["kind":"read-503"]);open();status("could not be verified")
        XCTAssertFalse(app.switches["historyConsent.toggle"].exists);XCTAssertFalse(app.staticTexts["historyConsent.current"].exists)
        let value=try await proof(f);XCTAssertEqual(value.history_posts,0);XCTAssertEqual(value.accounts["A"]?.actions.count,0)
        try audit("history-read-503-is-not-default-off")
    }
}
