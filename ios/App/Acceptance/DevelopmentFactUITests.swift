import XCTest
import Foundation

@MainActor final class DevelopmentFactUITests: XCTestCase {
    private let bundle = "space.go2china.fact.acceptance"
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private struct Fixture: Decodable {
        let case_id: String;let endpoint: String;let accounts: [String:String];let subjects: [String:String];let conversation: String;let date: String;let outside_date: String
    }
    private struct Proof: Decodable {
        let runtime_role: String;let pending: Int;let status: String?;let text: String;let message_id: String?
        let messages: Int;let posts: Int;let cancellations: Int;let model_calls: Int;let fact_calls: Int;let transport_calls: Int
        let budget_stage: String;let exposure: Int;let effects: [String];let originals_sha256: String;let registered_sha256: String;let ledger_sha256: String
        let forbidden_writes: Int;let worker_errors: [String];let real_wait_seconds: Double
    }
    private func call(_ path: String,_ fixture: Fixture? = nil,caseID: String? = nil,extra: [String:String] = [:]) async throws -> Data {
        var url = URLComponents(string:control + path)!
        var values = extra;values["case"] = fixture?.case_id ?? caseID!
        url.queryItems = values.map { .init(name:$0.key,value:$0.value) }
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        return data
    }
    private func prepare(_ name: String) async throws -> Fixture {
        continueAfterFailure = false;executionTimeAllowance = 600
        return try JSONDecoder().decode(Fixture.self,from:await call("/prepare",caseID:name))
    }
    private func proof(_ fixture: Fixture,settled: Bool = true) async throws -> Proof {
        let value = try JSONDecoder().decode(Proof.self,from:await call("/proof",fixture,extra:["settled":settled ? "1" : "0"]))
        XCTAssertEqual(value.runtime_role,"cj_m1_runtime");XCTAssertEqual(value.forbidden_writes,0)
        XCTAssertTrue(value.effects.isEmpty && value.worker_errors.isEmpty)
        if settled { XCTAssertEqual(value.pending,0) }
        return value
    }
    private func reveal(_ element: XCUIElement,id: String,fixed: Bool = false) {
        for attempt in 0..<40 {
            var top = app.navigationBars.firstMatch.exists ? app.navigationBars.firstMatch.frame.maxY : app.frame.minY + 60
            var bottom = app.tabBars.firstMatch.exists ? app.tabBars.firstMatch.frame.minY : app.frame.maxY - 20
            let header = app.otherElements.matching(identifier:"assistant.header").firstMatch
            let composer = app.otherElements.matching(identifier:"assistant.composer").firstMatch
            if !fixed && !app.navigationBars.firstMatch.exists && !["assistant.draft","assistant.send","assistant.intent"].contains(id) && header.exists && composer.exists {
                top = max(top,header.frame.maxY + 8);bottom = min(bottom,composer.frame.minY)
                let conversation = app.staticTexts.matching(identifier:"assistant.conversation").firstMatch
                if conversation.exists {bottom = min(bottom,conversation.frame.minY)}
            }
            let frame = element.exists ? element.frame : .zero
            if ["fact.output.0.source.0.url","fact.sources.open"].contains(id) && attempt % 6 == 0 {
                print("FACT_URL_VIEWPORT",attempt,frame,top,bottom,element.exists,element.isHittable)
            }
            if element.exists && element.isHittable && (fixed || frame.midY > top && frame.midY < bottom) {return}
            if fixed {_ = element.waitForExistence(timeout:1);continue}
            // Lazy Lists can omit a row on either side of the viewport. Search
            // both directions when its concrete snapshot is absent.
            let down = frame == .zero ? attempt >= 20 : frame.midY <= top
            let middle = (top + bottom) / 2,halfStep = min(125,(bottom - top) * 0.3)
            let start = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width * 0.85,dy:middle + (down ? -halfStep : halfStep)))
            let end = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width * 0.85,dy:middle + (down ? halfStep : -halfStep)))
            start.press(forDuration:0.05,thenDragTo:end)
        }
        let image = XCTAttachment(screenshot:app.screenshot());image.name = "not-visible-" + id;image.lifetime = .keepAlways;add(image)
        if id == "travel.selection.status" {
            for value in app.staticTexts.allElementsBoundByIndex.prefix(20) {print("TRAVEL_STATUS_STATIC",value.identifier,value.label,value.frame)}
            for value in app.otherElements.matching(NSPredicate(format:"identifier == %@ OR label BEGINSWITH %@",id,"已选旅行")).allElementsBoundByIndex.prefix(5) {print("TRAVEL_STATUS_OTHER",value.identifier,value.label,value.frame)}
        }
        XCTFail("Expected control within the visible page content: " + id)
    }
    private func tap(_ id: String) {
        let button: XCUIElement
        if ["Assistant","助手","Memory","记忆"].contains(id) { button = app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if ["assistant.panel.done","fact.sources.done"].contains(id) { button = app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else if ["Done","完成"].contains(id) { button = app.toolbars.buttons.matching(identifier:id).firstMatch }
        else { button = app.buttons.matching(identifier:id).firstMatch }
        XCTAssertTrue(button.waitForExistence(timeout:15),id)
        if ["assistant.panel.done","fact.sources.done"].contains(id) || ["Assistant","助手","Memory","记忆","Done","完成"].contains(id) {
            let fixedControl = XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == true AND hittable == true"),object:button)
            XCTAssertEqual(XCTWaiter.wait(for:[fixedControl],timeout:20),.completed,id)
        } else { reveal(button,id:id) }
        XCTAssertTrue(button.isHittable,id)
        let enabled = XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:button)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:20),.completed,id);button.tap()
    }
    @discardableResult private func text(_ id: String,contains: String,timeout: TimeInterval = 30) -> String {
        let panel = app.scrollViews.matching(identifier:"fact.sources.content").firstMatch
        let value = panel.exists ? panel.staticTexts.matching(identifier:id).firstMatch : app.staticTexts.matching(identifier:id).firstMatch
        XCTAssertTrue(value.waitForExistence(timeout:timeout),id)
        let expected = XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",contains),object:value)
        let waited = XCTWaiter.wait(for:[expected],timeout:timeout)
        if waited != .completed { capture("failed-" + id) }
        XCTAssertEqual(waited,.completed,id + " actual=" + value.label)
        if id.hasPrefix("fact.") { reveal(value,id:id);XCTAssertTrue(value.isHittable,id) }
        return value.label
    }
    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot:app.screenshot());image.name = name;image.lifetime = .keepAlways;add(image)
    }
    private func audit(_ name: String) throws {
        var count = 0;continueAfterFailure = true;defer { continueAfterFailure = false }
        try app.performAccessibilityAudit(for:.all) { issue in count += 1;print(name,issue.detailedDescription,issue.element?.label ?? "unavailable",issue.element?.frame ?? .zero);return false }
        continueAfterFailure = false;XCTAssertEqual(count,0)
    }
    private func launch(_ fixture: Fixture,language: String,large: Bool = false,restore: Bool = false,account: String = "A") throws {
        app?.terminate();app = XCUIApplication(bundleIdentifier:bundle)
        app.launchArguments = ["-cj.ui.language.v1",language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":fixture.endpoint,
            "G2C_DEV_ACCOUNTS":restore ? "{}" : String(data:try JSONEncoder().encode(fixture.accounts),encoding:.utf8)!,"G2C_DEV_FACT_TOOLS":"synthetic-fact-v1"]
        app.launch();XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:15))
        tap(language == "en" ? "Memory" : "记忆");tap("memory.account")
        if restore { tap("account.development.restore") }
        else { tap("account.development.signout");tap("account.development.signin." + account) }
        text("account.development.status",contains:fixture.subjects[account]!)
        tap(language == "en" ? "Assistant" : "助手")
    }
    private func openConversation(_ fixture: Fixture) {
        tap("assistant.serverHistory");tap("history.loadConversations");tap("history.conversation." + fixture.conversation);tap("assistant.panel.done")
    }
    private func send(_ value: String) {
        let view = app.textViews.matching(identifier:"assistant.draft").firstMatch
        let field = view.exists ? view : app.textFields.matching(identifier:"assistant.draft").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout:15));field.tap();field.typeText(value)
        XCTAssertEqual(Array((field.value as? String ?? "").utf8),Array(value.utf8))
        if app.toolbars.buttons.matching(identifier:"Done").firstMatch.exists { tap("Done") }
        else if app.toolbars.buttons.matching(identifier:"完成").firstMatch.exists { tap("完成") }
        tap("assistant.send")
    }
    private func completed(_ fixture: Fixture,language: String = "en",timeout: TimeInterval = 60) async throws {
        // Explicit original-result GET is a user action, not a MESSAGE/tool retry.
        // The real worker must already have completed; retain all stream FAILs.
        let before = try JSONDecoder().decode(Proof.self,from:await call("/wait-completed",fixture))
        XCTAssertEqual(before.status,"completed")
        tap("run.snapshot.read")
        text("run.display.status",contains:language == "en" ? "Completed" : "已完成",timeout:timeout)
        let after = try await proof(fixture)
        XCTAssertEqual(after.posts,before.posts);XCTAssertEqual(after.fact_calls,before.fact_calls)
        XCTAssertEqual(after.model_calls,before.model_calls);XCTAssertEqual(after.originals_sha256,before.originals_sha256)
        XCTAssertEqual(after.registered_sha256,before.registered_sha256);XCTAssertEqual(after.ledger_sha256,before.ledger_sha256)
    }
    private func prompt(_ fixture: Fixture,kind: String = "weather",scenario: String = "",conditions: String = "Asia/Shanghai") -> String {
        kind + " synthetic-city " + fixture.date + " " + conditions + " " + scenario
    }
    private func frame(_ proof: Proof) throws -> [String:Any] {
        for line in proof.text.split(separator:"\n") {
            let value = try XCTUnwrap(JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any])
            if value["version"] as? String == "FACT-output.1" {return try XCTUnwrap(value["result"] as? [String:Any])}
        }
        XCTFail("Expected actual FACT frame");throw NSError(domain:"FactAcceptance",code:1)
    }
    private func normal(_ name: String,language: String,large: Bool) async throws {
        let f = try await prepare(name);defer {app?.terminate()}
        try launch(f,language:language,large:large);openConversation(f)
        send(prompt(f));try await completed(f,language:language)
        let first = try await proof(f),result = try frame(first),original = try XCTUnwrap(result["original_value"] as? String)
        text("fact.origin",contains:language == "en" ? "Synthetic" : "合成")
        let displayed = text("fact.output.0.value",contains:"NOT a real forecast")
        XCTAssertEqual(Array(displayed.utf8),Array(original.utf8));XCTAssertTrue(displayed.contains("CNY 100") && displayed.contains(f.date))
        tap("fact.sources.open")
        text("fact.output.0.source.0.url",contains:"https://synthetic-fact.g2c.invalid/first")
        let sources = try XCTUnwrap(result["sources"] as? [[String:Any]]),source = try XCTUnwrap(sources.first)
        let retrieved = try XCTUnwrap(source["retrieved_at"] as? [String:Any]),declared = try XCTUnwrap(source["declarations"] as? [String:Any])
        let expiry = try XCTUnwrap(declared["expires_at"] as? [String:Any])
        text("fact.output.0.source.0.retrieved",contains:try XCTUnwrap(retrieved["iso8601"] as? String))
        text("fact.output.0.source.0.expiry",contains:try XCTUnwrap(expiry["iso8601"] as? String))
        text("fact.output.0.source.0.conditions",contains:"calendar_timezone=Asia/Shanghai")
        text("fact.machine.label",contains:language == "en" ? "not an official" : "非官方")
        capture("synthetic-fact-original-" + language);try audit("FACT_ORIGINAL_" + language)
        tap("fact.sources.done")
        send(prompt(f,kind:"synthetic rule",conditions:"Asia/Shanghai category=synthetic"));try await completed(f,language:language)
        tap("fact.sources.open")
        text("fact.output.0.source.0.conditions",contains:"category=synthetic")
        text("fact.output.0.value",contains:"NOT a real forecast")
        capture("synthetic-rule-explicit-scope-" + language);try audit("FACT_RULE_" + language)
        tap("fact.sources.done")
        if !large {
            send(prompt(f,scenario:"SYNTH_INJECTION"));try await completed(f)
            text("fact.output.0.status",contains:"supported");text("fact.output.0.value",contains:"NOT a real forecast")
        }
        let final = try await proof(f)
        XCTAssertEqual(final.messages,large ? 2 : 3);XCTAssertEqual(final.posts,final.messages)
        XCTAssertEqual(final.fact_calls,final.messages);XCTAssertEqual(final.model_calls,final.messages * 2)
        XCTAssertEqual(final.transport_calls,final.fact_calls)
    }
    func testEnglish() async throws {try await normal("testEnglish",language:"en",large:false)}
    func testChineseLarge() async throws {try await normal("testChineseLarge",language:"zh-Hans",large:true)}
    func testConditions() async throws {
        let f = try await prepare("testConditions");defer {app?.terminate()}
        try launch(f,language:"en");openConversation(f)
        send(prompt(f,conditions:""));try await completed(f);text("fact.output.0.status",contains:"unknown")
        text("fact.output.0.source.0.status",contains:"condition_not_supplied")
        send(prompt(f,kind:"synthetic rule"));try await completed(f);text("fact.output.0.status",contains:"unknown")
        send("weather synthetic-city " + f.outside_date + " Asia/Shanghai");try await completed(f)
        text("fact.output.0.status",contains:"Outside declared scope")
        send("weather synthetic-city");try await completed(f);text("fact.answer",contains:"Specify synthetic-city")
        text("fact.pending",contains:"No complete fact result")
        let value = try await proof(f);XCTAssertEqual(value.messages,4);XCTAssertEqual(value.fact_calls,3);XCTAssertEqual(value.model_calls,7)
        try audit("FACT_CONDITIONS")
    }
    func testOutcomes() async throws {
        let f = try await prepare("testOutcomes");defer {app?.terminate()}
        try launch(f,language:"en");openConversation(f)
        send(prompt(f,scenario:"SYNTH_EXPIRED"));try await completed(f);text("fact.output.0.status",contains:"Expired")
        send(prompt(f,scenario:"SYNTH_CONFLICT"));try await completed(f);text("fact.output.0.status",contains:"Conflicting")
        text("fact.output.0.value",contains:"No supported value")
        text("fact.output.0.source.1.original",contains:"different value")
        send(prompt(f,scenario:"SYNTH_MISSING"));try await completed(f);text("fact.output.0.outcome",contains:"No applicable source")
        text("fact.output.0.noSource",contains:"No source body")
        let value = try await proof(f);XCTAssertEqual(value.fact_calls,3);XCTAssertEqual(value.model_calls,6)
        XCTAssertEqual(value.transport_calls,3);try audit("FACT_OUTCOMES")
    }
    func testFailures() async throws {
        let f = try await prepare("testFailures");defer {app?.terminate()}
        try launch(f,language:"en");openConversation(f)
        for scenario in ["SYNTH_RATE","SYNTH_MALFORMED","SYNTH_OVERSIZE","SYNTH_REDIRECT"] {
            send(prompt(f,scenario:scenario));try await completed(f)
            text("fact.output.0.outcome",contains:scenario == "SYNTH_RATE" ? "rate limited" : "Invalid source response")
            text("fact.output.0.status",contains:"unknown");text("fact.output.0.noSource",contains:"No source body")
            XCTAssertFalse(app.staticTexts.matching(NSPredicate(format:"label CONTAINS %@","SYNTHETIC_PRIVATE_FACT_SENTINEL")).firstMatch.exists)
        }
        let value = try await proof(f);XCTAssertEqual(value.fact_calls,4);XCTAssertEqual(value.model_calls,8);XCTAssertEqual(value.posts,4)
        try audit("FACT_ACQUISITION_FAILURES")
    }
    func testUnknownReopen() async throws {
        let f = try await prepare("testUnknownReopen");defer {app?.terminate()}
        try launch(f,language:"en");openConversation(f);send(prompt(f,scenario:"SYNTH_TIMEOUT"))
        text("run.display.status",contains:"Result unknown");text("fact.pending",contains:"No complete fact result")
        let before = try await proof(f);XCTAssertEqual(before.status,"unknown");XCTAssertEqual(before.fact_calls,1);XCTAssertGreaterThan(before.exposure,0)
        try launch(f,language:"en",restore:true)
        tap("assistant.history");tap("recovery.action." + (try XCTUnwrap(before.message_id)));tap("assistant.panel.done")
        text("run.display.status",contains:"Result unknown")
        let after = try await proof(f)
        XCTAssertEqual(after.posts,before.posts);XCTAssertEqual(after.fact_calls,before.fact_calls);XCTAssertEqual(after.model_calls,before.model_calls)
        XCTAssertEqual(after.originals_sha256,before.originals_sha256);XCTAssertEqual(after.registered_sha256,before.registered_sha256);XCTAssertEqual(after.ledger_sha256,before.ledger_sha256)
        try audit("FACT_UNKNOWN_ORIGINAL")
    }
    func testOverLimit() async throws {
        let f = try await prepare("testOverLimit");defer {app?.terminate()}
        try launch(f,language:"en");openConversation(f);send(prompt(f))
        text("run.display.status",contains:"Failed")
        text("fact.output.0.value",contains:"NOT a real forecast")
        let value = try await proof(f);XCTAssertEqual(value.status,"failed");XCTAssertEqual(value.budget_stage,"answer")
        XCTAssertEqual(value.model_calls,1);XCTAssertEqual(value.fact_calls,1);XCTAssertEqual(value.posts,1)
        try audit("FACT_CORE_LIMIT")
    }
    func testCancel() async throws {
        let f = try await prepare("testCancel");defer {app?.terminate()}
        try launch(f,language:"en");openConversation(f);send(prompt(f))
        _ = try await call("/wait-source",f);tap("run.stop");text("run.display.status",contains:"Cancelled")
        _ = try await call("/release-source",f)
        let value = try await proof(f);XCTAssertEqual(value.status,"cancelled");XCTAssertEqual(value.fact_calls,0)
        XCTAssertEqual(value.posts,1);XCTAssertEqual(value.cancellations,1);try audit("FACT_CANCEL")
    }
    func testSwitchLate() async throws {
        let f = try await prepare("testSwitchLate");defer {app?.terminate()}
        try launch(f,language:"en");openConversation(f);send(prompt(f));try await completed(f)
        let before = try await proof(f)
        _ = try await call("/hold-read",f);tap("run.snapshot.read");_ = try await call("/wait-read",f)
        tap("Memory");text("account.development.status",contains:f.subjects["A"]!)
        tap("account.development.signout");tap("account.development.signin.B");text("account.development.status",contains:f.subjects["B"]!)
        _ = try await call("/release-read",f);tap("Assistant")
        XCTAssertFalse(app.staticTexts.matching(identifier:"fact.output.0.value").firstMatch.exists)
        tap("assistant.serverHistory");tap("history.loadConversations")
        XCTAssertFalse(app.buttons.matching(identifier:"history.conversation." + f.conversation).firstMatch.exists)
        let after = try await proof(f);XCTAssertEqual(after.posts,before.posts);XCTAssertEqual(after.fact_calls,before.fact_calls)
        XCTAssertEqual(after.originals_sha256,before.originals_sha256);try audit("FACT_LATE_OWNER")
    }
    func testReleaseClosed() async throws {
        let f = try await prepare("testReleaseClosed");defer {app?.terminate()}
        app = XCUIApplication(bundleIdentifier:bundle)
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,"G2C_DEV_FACT_TOOLS":"synthetic-fact-v1"]
        app.launch();XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:15))
        let value = try await proof(f);XCTAssertEqual(value.posts,0);XCTAssertEqual(value.model_calls,0);XCTAssertEqual(value.fact_calls,0)
        XCTAssertFalse(app.buttons.matching(identifier:"assistant.send").firstMatch.exists);try audit("FACT_RELEASE_CLOSED")
    }
}
