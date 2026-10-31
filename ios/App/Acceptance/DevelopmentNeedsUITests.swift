import XCTest
import Foundation

@MainActor final class DevelopmentNeedsUITests: XCTestCase {
    private let bundle = "space.go2china.needs.acceptance"
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private struct Fixture: Decodable {
        let case_id: String; let endpoint: String; let accounts: [String:String]; let subjects: [String:String]
        let conversation: String; let needs_id: String
    }
    private struct Original: Decodable {
        let action_id: String; let body_sha256: String; let status: Int?; let expected_version: Int
    }
    private struct Proof: Decodable {
        let runtime_role: String; let pending: Int; let status: String?; let text: String; let message_id: String?
        let messages: Int; let posts: Int; let manual_posts: Int; let external_posts: Int; let model_calls: Int
        let snapshot_status: Int; let snapshot_version: Int?; let snapshot_fields_json: String?
        let needs_records: Int; let needs_revisions: Int; let memory_records: Int; let trip_records: Int
        let exposure: Int; let effects: [String]; let originals_sha256: String; let registered_sha256: String; let ledger_sha256: String
        let manual_originals: [Original]; let manual_bytes_sha256: String; let forbidden_writes: Int; let worker_errors: [String]
    }
    private func call(_ path: String, _ f: Fixture? = nil, caseID: String? = nil, extra: [String:String] = [:]) async throws -> Data {
        var url = URLComponents(string:control + path)!
        var values = extra; values["case"] = f?.case_id ?? caseID!
        url.queryItems = values.map { .init(name:$0.key,value:$0.value) }
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        return data
    }
    private func prepare(_ name: String) async throws -> Fixture {
        continueAfterFailure = false; executionTimeAllowance = 900
        return try JSONDecoder().decode(Fixture.self,from:await call("/prepare",caseID:name))
    }
    private func proof(_ f: Fixture) async throws -> Proof {
        let value = try JSONDecoder().decode(Proof.self,from:await call("/proof",f,extra:["settled":"1"]))
        XCTAssertEqual(value.runtime_role,"cj_m1_runtime"); XCTAssertEqual(value.pending,0)
        XCTAssertEqual(value.forbidden_writes,0); XCTAssertEqual(value.memory_records,0); XCTAssertEqual(value.trip_records,0)
        XCTAssertTrue(value.effects.isEmpty && value.worker_errors.isEmpty)
        return value
    }
    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot:app.screenshot()); image.name = name; image.lifetime = .keepAlways; add(image)
    }
    private func reveal(_ element: XCUIElement, id: String) {
        for attempt in 0..<40 {
            let navigation = app.navigationBars.firstMatch
            var top = navigation.exists ? navigation.frame.maxY + 4 : app.frame.minY + 60
            var bottom = navigation.exists ? app.frame.maxY - 24 : app.tabBars.firstMatch.frame.minY
            let header = app.otherElements.matching(identifier:"assistant.header").firstMatch
            let composer = app.otherElements.matching(identifier:"assistant.composer").firstMatch
            if !navigation.exists && !["assistant.draft","assistant.send","assistant.intent"].contains(id) && header.exists && composer.exists {
                top = max(top,header.frame.maxY + 8); bottom = min(bottom,composer.frame.minY)
                let conversation = app.staticTexts.matching(identifier:"assistant.conversation").firstMatch
                if conversation.exists { bottom = min(bottom,conversation.frame.minY) }
            }
            let keyboard = app.keyboards.firstMatch
            if keyboard.exists { bottom = min(bottom,keyboard.frame.minY - 4) }
            let frame = element.exists ? element.frame : .zero
            if element.exists && element.isHittable && frame.midY > top && frame.midY < bottom { return }
            let down = frame == .zero ? attempt >= 20 : frame.midY <= top
            let middle = (top + bottom) / 2, step = min(150,(bottom-top)*0.35)
            let start = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:8,dy:middle+(down ? -step : step)))
            let end = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:8,dy:middle+(down ? step : -step)))
            start.press(forDuration:0.05,thenDragTo:end)
        }
        capture("not-visible-"+id); XCTFail("Expected visible control: "+id)
    }
    private func tap(_ id: String) {
        let element: XCUIElement
        let fixed = ["Assistant","助手","Memory","记忆","assistant.history","assistant.panel.done","needs.keyboard.done","Done","完成"].contains(id)
        if ["Assistant","助手","Memory","记忆"].contains(id) { element = app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if id == "assistant.panel.done" { element = app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else if ["needs.keyboard.done","Done","完成"].contains(id) { element = app.toolbars.buttons.matching(identifier:id).firstMatch }
        else {
            let button = app.buttons.matching(identifier:id).firstMatch
            if button.waitForExistence(timeout:2) { element = button }
            else {
                let other = app.otherElements.matching(identifier:id).firstMatch
                if other.exists { element = other }
                else {
                    let label = app.staticTexts.matching(identifier:id).firstMatch
                    element = label.exists ? label : app.disclosureTriangles.matching(identifier:id).firstMatch
                }
            }
        }
        XCTAssertTrue(element.waitForExistence(timeout:15),id)
        if !fixed { reveal(element,id:id) }
        let ready = XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == true AND hittable == true AND enabled == true"),object:element)
        XCTAssertEqual(XCTWaiter.wait(for:[ready],timeout:20),.completed,id)
        element.tap()
    }
    @discardableResult private func text(_ id: String, contains: String, timeout: TimeInterval = 30) -> String {
        let panel = app.scrollViews.matching(identifier:"needs.content").firstMatch
        let value = panel.exists ? panel.staticTexts.matching(identifier:id).firstMatch : app.staticTexts.matching(identifier:id).firstMatch
        let exists = value.waitForExistence(timeout:timeout)
        if !exists { capture("missing-"+id) }
        XCTAssertTrue(exists,id)
        let expected = XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",contains),object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[expected],timeout:timeout),.completed,id+" actual="+value.label)
        if id.hasPrefix("needs.") { reveal(value,id:id); XCTAssertTrue(value.isHittable,id) }
        return value.label
    }
    private func field(_ id: String) -> XCUIElement {
        let view = app.textViews.matching(identifier:id).firstMatch
        return view.exists ? view : app.textFields.matching(identifier:id).firstMatch
    }
    private func dismissKeyboard(_ language: String) {
        guard app.keyboards.firstMatch.exists else { return }
        if app.scrollViews.matching(identifier:"needs.content").firstMatch.exists {
            tap("needs.keyboard.done")
        } else {
            tap(language == "en" ? "Done" : "完成")
        }
        let hidden = XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == false"),object:app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for:[hidden],timeout:10),.completed,"Keyboard must no longer cover page controls")
    }
    private func replace(_ id: String, value: String, language: String) {
        let target = field(id); XCTAssertTrue(target.waitForExistence(timeout:15)); reveal(target,id:id); target.tap()
        target.coordinate(withNormalizedOffset:CGVector(dx:0.95,dy:0.5)).tap()
        let previous = target.value as? String ?? ""
        target.typeText(String(repeating:XCUIKeyboardKey.delete.rawValue,count:previous.count)+value)
        XCTAssertEqual(Array((target.value as? String ?? "").utf8),Array(value.utf8)); dismissKeyboard(language)
    }
    private func appendStatement(_ value: String, language: String) {
        let target = field("needs.editor.statement"); reveal(target,id:"needs.editor.statement"); target.tap()
        target.coordinate(withNormalizedOffset:CGVector(dx:0.95,dy:0.95)).tap()
        target.typeText(value); dismissKeyboard(language)
    }
    private func editKnown(_ field: String, value: String, language: String) {
        tap("needs.editor."+field+".section")
        replace("needs.editor."+field+".value",value:value,language:language)
    }
    private func audit(_ name: String) throws {
        var count = 0; continueAfterFailure = true; defer { continueAfterFailure = false }
        try app.performAccessibilityAudit(for:.all) { issue in count += 1; print(name,issue.detailedDescription,issue.element?.label ?? "unavailable"); return false }
        continueAfterFailure = false; XCTAssertEqual(count,0)
    }
    private func launch(_ f: Fixture, language: String = "en", large: Bool = false, restore: Bool = false, timezone: String? = nil) throws {
        app?.terminate(); app = XCUIApplication(bundleIdentifier:bundle)
        app.launchArguments = ["-cj.ui.language.v1",language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_ACCOUNTS":restore ? "{}" : String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,
            "G2C_DEV_NEEDS_PROFILE":"manual-v1","G2C_DEV_NEEDS_ID":f.needs_id,"G2C_DEV_NEEDS_PREVIEW":"synthetic-needs-v1"]
        if let timezone { app.launchEnvironment["TZ"] = timezone }
        app.launch(); XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:15))
        tap(language == "en" ? "Memory" : "记忆"); tap("memory.account")
        if restore { tap("account.development.restore") }
        else { tap("account.development.signout"); tap("account.development.signin.A") }
        text("account.development.status",contains:f.subjects["A"]!)
        tap(language == "en" ? "Assistant" : "助手")
    }
    private func rich(_ language: String) -> String {
        language == "en"
            ? "we are 3; budget USD 1000.00 total; paid USD 100.00; includes international transport; arrival 2026-11-02 23:30 Asia/Shanghai; departure 2026-11-05 00:00 Asia/Shanghai; booked hotel for mother; fixed appointment for self 2026-11-03 08:00 Asia/Shanghai; this trip mother has a leg injury; remember I avoid spicy"
            : "本次3人；预算 CNY 8000.00 总计；已付 CNY 100.00；包含国际交通；抵达 2026-11-02 23:30 Asia/Shanghai；离境 2026-11-05 00:00 Asia/Shanghai；已订酒店 母亲；固定交通 全体 2026-11-03 08:00 Asia/Shanghai；本次母亲腿伤；请记住本人不吃辣"
    }
    private func preview(_ f: Fixture, source: String, language: String = "en") async throws {
        tap("assistant.serverHistory"); tap("history.loadConversations"); tap("history.conversation."+f.conversation); tap("assistant.panel.done")
        let target = field("assistant.draft"); XCTAssertTrue(target.waitForExistence(timeout:15)); target.tap(); target.typeText(source)
        XCTAssertEqual(Array((target.value as? String ?? "").utf8),Array(source.utf8)); dismissKeyboard(language); tap("assistant.send")
        _ = try await call("/wait-completed",f)
        let before = try await proof(f); tap("run.snapshot.read"); text("run.display.status",contains:language == "en" ? "Completed" : "已完成")
        let after = try await proof(f)
        XCTAssertEqual(after.posts,before.posts); XCTAssertEqual(after.model_calls,before.model_calls); XCTAssertEqual(after.ledger_sha256,before.ledger_sha256)
        tap("needs.preview.open"); text("needs.preview.status",contains:language == "en" ? "UNCONFIRMED" : "未确认")
    }
    private func beginAndCopy(_ language: String = "en") {
        tap("needs.beginNew"); tap("needs.preview.copy"); tap("needs.editor.open")
    }
    private func save(_ language: String = "en") {
        tap("needs.save"); text("needs.container.state",contains:language == "en" ? "Original action verified" : "原动作与历史版本已核对")
    }
    private func readDetails(_ version: Int) {
        tap("needs.read"); tap("needs.detail.open"); text("needs.detail.version",contains:String(version))
    }
    private func normal(_ name: String, language: String, large: Bool) async throws {
        let f = try await prepare(name); defer { app?.terminate() }
        try launch(f,language:language,large:large)
        try await preview(f,source:rich(language),language:language)
        let before = try await proof(f); XCTAssertEqual(before.needs_records,0); XCTAssertEqual(before.manual_posts,0); XCTAssertEqual(before.model_calls,1)
        text("needs.preview.memoryDeferred",contains:language == "en" ? "NOT saved" : "尚未保存")
        tap("needs.preview.fields.open"); text("needs.preview.currency",contains:language == "en" ? "USD" : "CNY")
        text("needs.preview.paid",contains:"100.00"); text("needs.preview.includes",contains:language == "en" ? "international transport" : "国际交通")
        text("needs.preview.arrival.time",contains:"23:30"); text("needs.preview.fixed.0.subjects",contains:language == "en" ? "mother" : "母亲")
        text("needs.preview.temporary.0",contains:language == "en" ? "mother" : "母亲")
        capture("synthetic-needs-unconfirmed-"+language)
        tap("needs.preview.fields.open")
        beginAndCopy(language); editKnown("partySize",value:"4",language:language); appendStatement(language == "en" ? "\nSYNTHETIC manual correction: party size 4" : "\n合成手工纠正：本次4人",language:language)
        save(language); readDetails(1)
        text("needs.detail.partySize",contains:"4"); text("needs.detail.source",contains:language == "en" ? "user provided" : "用户提供")
        text("needs.detail.includes",contains:language == "en" ? "international transport" : "国际交通")
        text("needs.detail.arrival.time",contains:"23:30"); text("needs.detail.arrival.timezone",contains:"Asia/Shanghai")
        capture("synthetic-needs-saved-"+language); try audit("NEEDS_SAVED_"+language)
        let saved = try await proof(f); XCTAssertEqual(saved.needs_revisions,1); XCTAssertEqual(saved.manual_posts,1)
        XCTAssertEqual(saved.ledger_sha256,before.ledger_sha256); XCTAssertEqual(saved.model_calls,1)
        if !large {
            tap("needs.detail.open"); tap("needs.useCurrent"); tap("needs.editor.open")
            editKnown("currency",value:"CNY",language:language)
            text("needs.currencyReview",contains:"does not convert")
            XCTAssertFalse(app.buttons.matching(identifier:"needs.save").firstMatch.isEnabled)
            let unchanged = try await proof(f); XCTAssertEqual(unchanged.manual_posts,1)
            editKnown("total",value:"7000.00",language:language); editKnown("paid",value:"500.00",language:language)
            appendStatement("SYNTHETIC user-provided CNY estimates; no conversion",language:language)
            save(); readDetails(2); text("needs.detail.currency",contains:"CNY"); text("needs.detail.total",contains:"7000.00")
            let corrected = try await proof(f); XCTAssertEqual(corrected.manual_posts,2); XCTAssertEqual(corrected.needs_revisions,2)
            XCTAssertEqual(corrected.ledger_sha256,before.ledger_sha256); XCTAssertEqual(corrected.model_calls,1)
        }
    }
    func testEnglish() async throws { try await normal("testEnglish",language:"en",large:false) }
    func testChineseLarge() async throws { try await normal("testChineseLarge",language:"zh-Hans",large:true) }
    func testClarifications() async throws {
        let f = try await prepare("testClarifications"); defer { app?.terminate() }
        try launch(f); try await preview(f,source:"budget USD 1000; paid CNY 50; I do not eat spicy; booked hotel")
        for i in 0..<4 { text("needs.preview.question.\(i)",contains:["total or per person","currency basis","this trip","specific companion"][i]) }
        tap("needs.preview.fields.open"); text("needs.preview.total",contains:"Not recorded"); text("needs.preview.paid",contains:"Uncertain")
        tap("needs.preview.fields.open"); beginAndCopy(); appendStatement("SYNTHETIC explicit correction only",language:"en"); save(); readDetails(1)
        text("needs.detail.basis",contains:"Unknown"); text("needs.detail.paid",contains:"Uncertain")
        let p = try await proof(f); XCTAssertEqual(p.manual_posts,1); XCTAssertEqual(p.model_calls,1); try audit("NEEDS_CLARIFICATION")
    }
    func testConflictReplay() async throws {
        let f = try await prepare("testConflictReplay"); defer { app?.terminate() }
        try launch(f); try await preview(f,source:"we are 3; dates undecided"); beginAndCopy(); appendStatement("SYNTHETIC save",language:"en"); save()
        tap("needs.read"); tap("needs.useCurrent"); tap("needs.editor.open"); editKnown("partySize",value:"4",language:"en"); appendStatement("SYNTHETIC stale edit",language:"en")
        _ = try await call("/external-correction",f); tap("needs.save"); text("needs.container.state",contains:"conflict")
        text("needs.editor.basis",contains:"version 1"); tap("needs.read"); text("needs.editor.basis",contains:"version 1")
        tap("needs.useCurrent"); tap("needs.editor.open"); editKnown("partySize",value:"4",language:"en"); appendStatement("SYNTHETIC new explicit basis",language:"en"); save()
        let before = try await proof(f); XCTAssertEqual(before.needs_revisions,3); XCTAssertEqual(before.external_posts,1)
        let original = try XCTUnwrap(before.manual_originals.first)
        tap("needs.originals.read"); tap("needs.original.query."+original.action_id); text("needs.container.state",contains:"Original action verified")
        text("needs.editor.basis",contains:"version 2"); tap("needs.original.replay."+original.action_id); text("needs.container.state",contains:"Original action verified")
        let after = try await proof(f); XCTAssertEqual(after.needs_revisions,3); XCTAssertEqual(after.manual_originals.last?.body_sha256,original.body_sha256)
        XCTAssertEqual(after.ledger_sha256,before.ledger_sha256); XCTAssertEqual(after.model_calls,1); try audit("NEEDS_CONFLICT_ORIGINAL")
    }
    func testUnknownReopen() async throws {
        let f = try await prepare("testUnknownReopen"); defer { app?.terminate() }
        try launch(f); try await preview(f,source:"we are 3; dates undecided"); beginAndCopy(); appendStatement("SYNTHETIC ACK-loss save",language:"en")
        tap("needs.save"); text("needs.container.state",contains:"Result unknown")
        let before = try await proof(f); XCTAssertEqual(before.manual_posts,1); XCTAssertEqual(before.snapshot_version,1)
        let original = try XCTUnwrap(before.manual_originals.first)
        try launch(f,restore:true); tap("assistant.needs"); tap("needs.originals.read"); tap("needs.original.query."+original.action_id)
        text("needs.container.state",contains:"Original action verified")
        let after = try await proof(f); XCTAssertEqual(after.manual_posts,1); XCTAssertEqual(after.manual_bytes_sha256,before.manual_bytes_sha256)
        XCTAssertEqual(after.model_calls,before.model_calls); XCTAssertEqual(after.ledger_sha256,before.ledger_sha256); try audit("NEEDS_UNKNOWN_REOPEN")
    }
    func testCancelWaiting() async throws {
        let f = try await prepare("testCancelWaiting"); defer { app?.terminate() }
        try launch(f); try await preview(f,source:"we are 3; dates undecided"); beginAndCopy(); appendStatement("SYNTHETIC stop waiting",language:"en")
        tap("needs.save"); _ = try await call("/wait-manual",f); tap("needs.cancel"); text("needs.container.state",contains:"Result unknown")
        _ = try await call("/release-manual",f)
        let before = try await proof(f); XCTAssertEqual(before.snapshot_version,1); XCTAssertEqual(before.manual_posts,1)
        tap("needs.save"); text("needs.manualIssue",contains:"Reconcile all original actions")
        let blocked = try await proof(f); XCTAssertEqual(blocked.manual_posts,1); XCTAssertEqual(blocked.manual_bytes_sha256,before.manual_bytes_sha256)
        tap("needs.originals.read"); tap("needs.original.query."+(try XCTUnwrap(before.manual_originals.first?.action_id)))
        text("needs.container.state",contains:"Original action verified"); try audit("NEEDS_CANCEL_UNKNOWN")
    }
    func testOwnerLate() async throws {
        let f = try await prepare("testOwnerLate"); defer { app?.terminate() }
        try launch(f); try await preview(f,source:"we are 3; dates undecided"); beginAndCopy(); appendStatement("SYNTHETIC owner A",language:"en"); save()
        let before = try await proof(f); _ = try await call("/hold-read",f); tap("needs.read"); _ = try await call("/wait-read",f)
        tap("assistant.panel.done"); tap("Memory"); text("account.development.status",contains:f.subjects["A"]!)
        tap("account.development.signout"); tap("account.development.signin.B"); text("account.development.status",contains:f.subjects["B"]!)
        _ = try await call("/release-read",f); tap("Assistant"); tap("assistant.needs")
        XCTAssertFalse(app.staticTexts.matching(identifier:"needs.receipt").firstMatch.exists)
        tap("needs.originals.read"); XCTAssertFalse(app.buttons.matching(identifier:"needs.original.query."+(try XCTUnwrap(before.manual_originals.first?.action_id))).firstMatch.exists)
        tap("needs.beginNew"); tap("needs.editor.open"); tap("needs.editor.partySize.section"); tap("needs.editor.partySize.state"); tap("User provided")
        replace("needs.editor.partySize.value",value:"9",language:"en"); appendStatement("SYNTHETIC owner B separate record",language:"en"); save(); readDetails(1)
        text("needs.detail.partySize",contains:"9")
        let after = try await proof(f); XCTAssertEqual(after.manual_posts,before.manual_posts+1); XCTAssertEqual(after.snapshot_version,1)
        let fields = try XCTUnwrap(after.snapshot_fields_json); XCTAssertTrue(fields.contains("3")); try audit("NEEDS_OWNER_LATE")
    }
    func testDeviceTimezones() async throws {
        let f = try await prepare("testDeviceTimezones"); defer { app?.terminate() }
        try launch(f,timezone:"Pacific/Honolulu"); try await preview(f,source:rich("en")); beginAndCopy(); appendStatement("SYNTHETIC timezone test",language:"en"); save(); readDetails(1)
        text("needs.deviceTimezone",contains:"Pacific/Honolulu"); text("needs.detail.arrival.time",contains:"23:30")
        let before = try await proof(f)
        try launch(f,restore:true,timezone:"Europe/Paris"); tap("assistant.needs"); readDetails(1)
        text("needs.deviceTimezone",contains:"Europe/Paris"); text("needs.detail.arrival.date",contains:"2026-11-02"); text("needs.detail.arrival.time",contains:"23:30"); text("needs.detail.arrival.timezone",contains:"Asia/Shanghai")
        let after = try await proof(f); XCTAssertEqual(after.snapshot_fields_json,before.snapshot_fields_json); XCTAssertEqual(after.manual_posts,1); XCTAssertEqual(after.model_calls,1)
    }
    func testReleaseClosed() async throws {
        let f = try await prepare("testReleaseClosed"); defer { app?.terminate() }
        app = XCUIApplication(bundleIdentifier:bundle)
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,"G2C_DEV_NEEDS_PROFILE":"manual-v1","G2C_DEV_NEEDS_ID":f.needs_id,"G2C_DEV_NEEDS_PREVIEW":"synthetic-needs-v1"]
        app.launch(); XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:15))
        let p = try await proof(f); XCTAssertEqual(p.manual_posts,0); XCTAssertEqual(p.model_calls,0); XCTAssertEqual(p.messages,0)
        XCTAssertFalse(app.buttons.matching(identifier:"assistant.send").firstMatch.exists); try audit("NEEDS_RELEASE_CLOSED")
    }
}
