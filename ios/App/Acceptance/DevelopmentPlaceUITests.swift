import XCTest
import Foundation

@MainActor final class DevelopmentPlaceUITests: XCTestCase {
    private let bundle = "space.go2china.place.acceptance"
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private struct Fixture: Decodable {
        let case_id: String;let endpoint: String;let accounts: [String:String];let subjects: [String:String];let conversation: String
    }
    private struct Proof: Decodable {
        let runtime_role: String;let pending: Int;let status: String?;let text: String;let message_id: String?
        let messages: Int;let posts: Int;let cancellations: Int;let model_calls: Int;let place_calls: Int;let transport_calls: Int
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
    private func tap(_ id: String) {
        let button: XCUIElement
        if ["Assistant","助手","Memory","记忆"].contains(id) { button = app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if id == "assistant.panel.done" { button = app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else { button = app.buttons.matching(identifier:id).firstMatch }
        XCTAssertTrue(button.waitForExistence(timeout:15),id)
        for _ in 0..<18 { if button.isHittable { break };app.swipeUp() }
        XCTAssertTrue(button.isHittable,id)
        let enabled = XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:button)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:20),.completed,id);button.tap()
    }
    @discardableResult private func text(_ id: String,contains: String,timeout: TimeInterval = 30) -> String {
        let value = app.staticTexts.matching(identifier:id).firstMatch
        XCTAssertTrue(value.waitForExistence(timeout:timeout),id)
        let expected = XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",contains),object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[expected],timeout:timeout),.completed,id)
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
            "G2C_DEV_ACCOUNTS":restore ? "{}" : String(data:try JSONEncoder().encode(fixture.accounts),encoding:.utf8)!,"G2C_DEV_PLACE_TOOLS":"synthetic-v1"]
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
        if app.buttons.matching(identifier:"Done").firstMatch.exists { tap("Done") }
        else if app.buttons.matching(identifier:"完成").firstMatch.exists { tap("完成") }
        tap("assistant.send")
    }
    private func completed(language: String = "en",timeout: TimeInterval = 60) {
        text("run.display.status",contains:language == "en" ? "Completed" : "已完成",timeout:timeout)
    }
    private func normal(_ name: String,language: String,large: Bool) async throws {
        let fixture = try await prepare(name);defer { app?.terminate() }
        try launch(fixture,language:language,large:large);openConversation(fixture)
        send("Find synthetic hotel / 查询合成酒店 e\u{301}");completed(language:language)
        text("place.origin",contains:language == "en" ? "Synthetic" : "合成")
        text("place.output.0.SYNTH_EAST.name",contains:"合成酒店")
        text("place.output.0.SYNTH_EAST.address",contains:"合成东路一号")
        text("place.output.0.SYNTH_EAST.centre",contains:"116.100000,39.100000")
        text("place.output.0.SYNTH_EAST.entrance",contains:"116.100100,39.100100")
        text("place.output.0.SYNTH_WEST.name",contains:"合成酒店")
        text("place.output.0.SYNTH_WEST.address",contains:language == "en" ? "Empty array" : "空数组")
        text("place.output.0.SYNTH_EAST.officialName",contains:language == "en" ? "Unknown" : "未知")
        text("place.machine.label",contains:language == "en" ? "not official" : "非官方")
        capture("places-same-name-branches-" + language);try audit("PLACE_BRANCHES_" + language)
        if !large {
            send("SYNTH_EAST details");completed()
            text("place.output.0.SYNTH_EAST.providerID",contains:"SYNTH_EAST")
            text("place.output.0.SYNTH_EAST.entrance",contains:"116.100100,39.100100")
            text("place.output.0.source",contains:"/v3/place/detail")
            send("SYNTH_WEST details");completed()
            text("place.output.0.SYNTH_WEST.providerID",contains:"SYNTH_WEST")
            let missing = text("place.output.0.SYNTH_WEST.address",contains:"Empty array")
            XCTAssertFalse(missing.contains("合成东路一号"))
            text("place.output.0.SYNTH_WEST.entrance",contains:"Missing")
        }
        send("synthetic route / 查询合成路线");completed(language:language)
        text("place.output.0.origin",contains:"SYNTH_EAST · entrance · 116.100100,39.100100")
        text("place.output.0.destination",contains:"SYNTH_WEST · poi_center · 116.200000,39.200000")
        text("place.output.0.distance",contains:"100 m");text("place.output.0.duration",contains:"90 s")
        text("place.output.0.departure",contains:language == "en" ? "query time" : "查询时")
        text("place.output.0.future",contains:language == "en" ? "not guaranteed" : "不保证")
        capture("route-original-roles-" + language);try audit("PLACE_ROUTE_" + language)
        let saved = try await proof(fixture)
        XCTAssertEqual(saved.messages,large ? 2 : 4);XCTAssertEqual(saved.place_calls,saved.messages)
        XCTAssertEqual(saved.model_calls,saved.messages * 2);XCTAssertEqual(saved.posts,saved.messages)
        XCTAssertEqual(saved.transport_calls,saved.place_calls)
    }
    func testEnglish() async throws { try await normal("testEnglish",language:"en",large:false) }
    func testChineseLarge() async throws { try await normal("testChineseLarge",language:"zh-Hans",large:true) }
    func testOutcomes() async throws {
        let fixture = try await prepare("testOutcomes");defer { app?.terminate() }
        try launch(fixture,language:"en");openConversation(fixture)
        send("SYNTH_MISSING");completed();text("place.output.0.outcome",contains:"No results")
        send("SYNTH_BAD_JSON");completed();text("place.output.0.outcome",contains:"Invalid provider response")
        let saved = try await proof(fixture);XCTAssertEqual(saved.place_calls,2);XCTAssertEqual(saved.model_calls,4)
        XCTAssertEqual(saved.posts,2);try audit("PLACE_OUTCOMES")
    }
    func testUnknownReopen() async throws {
        let fixture = try await prepare("testUnknownReopen");defer { app?.terminate() }
        try launch(fixture,language:"en");openConversation(fixture);send("SYNTH_TIMEOUT")
        text("run.display.status",contains:"Result unknown")
        text("place.pending",contains:"No complete")
        let before = try await proof(fixture);XCTAssertEqual(before.status,"unknown");XCTAssertEqual(before.place_calls,1)
        XCTAssertGreaterThan(before.exposure,0)
        try launch(fixture,language:"en",restore:true)
        tap("assistant.history");tap("recovery.action." + (try XCTUnwrap(before.message_id)));tap("assistant.panel.done")
        text("run.display.status",contains:"Result unknown")
        let after = try await proof(fixture)
        XCTAssertEqual(after.posts,before.posts);XCTAssertEqual(after.model_calls,before.model_calls);XCTAssertEqual(after.place_calls,before.place_calls)
        XCTAssertEqual(after.ledger_sha256,before.ledger_sha256);XCTAssertEqual(after.originals_sha256,before.originals_sha256)
        XCTAssertEqual(after.registered_sha256,before.registered_sha256);try audit("PLACE_UNKNOWN_ORIGINAL")
    }
    func testOverLimit() async throws {
        let fixture = try await prepare("testOverLimit");defer { app?.terminate() }
        try launch(fixture,language:"en");openConversation(fixture);send("SYNTH_DOUBLE_TOOL")
        text("run.display.status",contains:"Failed");text("run.budget.status",contains:"Budget exhausted")
        text("place.output.0.SYNTH_EAST.providerID",contains:"SYNTH_EAST")
        let saved = try await proof(fixture);XCTAssertEqual(saved.status,"failed");XCTAssertEqual(saved.budget_stage,"answer")
        XCTAssertEqual(saved.model_calls,1);XCTAssertEqual(saved.place_calls,1);XCTAssertEqual(saved.posts,1)
        try audit("PLACE_REAL_CORE_LIMIT")
    }
    func testCancel() async throws {
        let fixture = try await prepare("testCancel");defer { app?.terminate() }
        try launch(fixture,language:"en");openConversation(fixture);send("Find synthetic hotel")
        _ = try await call("/wait-source",fixture)
        tap("run.stop");text("run.display.status",contains:"Cancelled")
        _ = try await call("/release-source",fixture)
        let saved = try await proof(fixture);XCTAssertEqual(saved.status,"cancelled");XCTAssertEqual(saved.place_calls,0)
        XCTAssertEqual(saved.cancellations,1);XCTAssertEqual(saved.posts,1);try audit("PLACE_CANCEL_BEFORE_INVOKE")
    }
    func testExpired() async throws {
        let fixture = try await prepare("testExpired");defer { app?.terminate() }
        try launch(fixture,language:"en");openConversation(fixture);send("Find synthetic hotel")
        completed(timeout:180);text("place.output.0.outcome",contains:"Expired result")
        let saved = try await proof(fixture);XCTAssertGreaterThanOrEqual(saved.real_wait_seconds,60)
        XCTAssertEqual(saved.place_calls,1);XCTAssertEqual(saved.model_calls,2);try audit("PLACE_PHYSICAL_AGE")
    }
    func testSwitchLate() async throws {
        let fixture = try await prepare("testSwitchLate");defer { app?.terminate() }
        try launch(fixture,language:"en");openConversation(fixture);send("Find synthetic hotel");completed()
        let before = try await proof(fixture)
        _ = try await call("/hold-read",fixture);tap("run.snapshot.read");_ = try await call("/wait-read",fixture)
        tap("Memory");tap("memory.account");tap("account.development.signout");tap("account.development.signin.B")
        text("account.development.status",contains:fixture.subjects["B"]!)
        _ = try await call("/release-read",fixture);tap("Assistant")
        XCTAssertFalse(app.staticTexts.matching(identifier:"place.output.0.SYNTH_EAST.name").firstMatch.exists)
        tap("assistant.serverHistory");tap("history.loadConversations")
        XCTAssertFalse(app.buttons.matching(identifier:"history.conversation." + fixture.conversation).firstMatch.exists)
        let after = try await proof(fixture);XCTAssertEqual(after.posts,before.posts);XCTAssertEqual(after.place_calls,before.place_calls)
        XCTAssertEqual(after.originals_sha256,before.originals_sha256);try audit("PLACE_LATE_OWNER_REPLY")
    }
    func testReleaseClosed() async throws {
        let fixture = try await prepare("testReleaseClosed");defer { app?.terminate() }
        app = XCUIApplication(bundleIdentifier:bundle)
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":fixture.endpoint,
            "G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(fixture.accounts),encoding:.utf8)!,"G2C_DEV_PLACE_TOOLS":"synthetic-v1"]
        app.launch();XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:15))
        let saved = try await proof(fixture);XCTAssertEqual(saved.posts,0);XCTAssertEqual(saved.model_calls,0);XCTAssertEqual(saved.place_calls,0)
        XCTAssertFalse(app.buttons.matching(identifier:"assistant.send").firstMatch.exists)
        try audit("PLACE_RELEASE_CLOSED")
    }
}
