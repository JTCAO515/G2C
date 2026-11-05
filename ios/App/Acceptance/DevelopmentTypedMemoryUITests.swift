import XCTest
import Foundation

/// Actual signed local producers only; no injected Memory records or UI model.
@MainActor final class DevelopmentTypedMemoryUITests: XCTestCase {
    private let control = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    #if G2C_M4_DEVICE_ACCEPTANCE
    private lazy var deviceSession = M4DeviceTestSession(test: self, control: control)
    #endif
    private var chinese = false
    private func localized(_ english: String,_ zh: String) -> String {chinese ? zh : english}
    private struct Fixture: Decodable {
        let endpoint: String;let memory_endpoint: String;let accounts: [String:String];let subjects: [String:String]
        let question_count:Int?
        let travel_ids: [String];let travel_profile: String;let memory_profile: String;let legacy_profile: String
    }
    private func reveal(_ element: XCUIElement,id: String,fixed: Bool = false) {
        for attempt in 0..<40 {
            var top = app.navigationBars.firstMatch.exists ? app.navigationBars.firstMatch.frame.maxY : app.frame.minY + 60
            var bottom = app.tabBars.firstMatch.exists ? app.tabBars.firstMatch.frame.minY : app.frame.maxY - 20
            let header = app.otherElements.matching(identifier:"assistant.header").firstMatch
            let composer = app.otherElements.matching(identifier:"assistant.composer").firstMatch
            if !fixed && !app.navigationBars.firstMatch.exists && !["assistant.draft","assistant.send","assistant.intent"].contains(id) && header.exists && composer.exists {
                top = max(top,header.frame.maxY + 8);bottom = min(bottom,composer.frame.minY)
            }
            let frame = element.exists ? element.frame : .zero
            if element.exists && element.isHittable && (fixed || frame.midY > top && frame.midY < bottom) {return}
            if fixed {_ = element.waitForExistence(timeout:1);continue}
            // Lazy Lists can omit a row on either side of the viewport. Search
            // both directions when its concrete snapshot is absent.
            let down = frame == .zero ? (attempt / 6) % 2 == 1 : frame.midY <= top
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
        let id = chinese ? (["Memory":"记忆","Assistant":"助手","Trips":"行程","Done":"完成"][id] ?? id) : id
        let target: XCUIElement
        if ["Memory","Assistant","Trips","记忆","助手","行程"].contains(id) { target = app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if id == "assistant.panel.done" { target = app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else if ["Done","完成"].contains(id) {target = app.toolbars.buttons.matching(identifier:id).firstMatch}
        else { target = app.buttons.matching(identifier:id).firstMatch }
        let fixed = ["Memory","Assistant","Trips","记忆","助手","行程","assistant.panel.done","Done","完成"].contains(id)
        reveal(target,id:id,fixed:fixed)
        XCTAssertTrue(target.waitForExistence(timeout:10),id);XCTAssertTrue(target.isHittable,id)
        let enabled = XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:20),.completed,id);target.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
        #if G2C_M4_DEVICE_ACCEPTANCE
        if id.hasPrefix("account.development.signin.") || id == "account.development.restore" {
            deviceSession.waitForAppNetworkConsent()
        }
        if ["Memory","记忆"].contains(id) {
            // Tab selection can restore the Account page retained by this tab.
            // Return through its exact back control before using Memory-root actions.
            let account=app.navigationBars.matching(identifier:localized("Account","账号")).firstMatch
            if account.waitForExistence(timeout:2) {
                XCTAssertEqual(account.buttons.count,1)
                let back=account.buttons.element(boundBy:0)
                XCTAssertTrue(back.isEnabled && back.isHittable);back.tap()
                XCTAssertTrue(app.navigationBars.matching(identifier:localized("Memory","记忆")).firstMatch.waitForExistence(timeout:10))
            }
        }
        #endif
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
        let answer = id == "run.display.text" || id == "run.stream.text"
        let label = answer ? app.textViews.matching(identifier:id).firstMatch : app.staticTexts.matching(identifier:id).firstMatch
        // Form sections are lazy, including the original-result footer. Read
        // actual visible content rather than relying on an offscreen snapshot.
        reveal(label,id:id)
        XCTAssertTrue(label.waitForExistence(timeout:15),id)
        let value = XCTNSPredicateExpectation(predicate:NSPredicate(format:answer ? "value CONTAINS %@" : "label CONTAINS %@",expected),object:label)
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
        return try JSONDecoder().decode(Fixture.self,from:await call("/prepare"))
    }
    private func reviewSave(_ value: String,scope: String) {
        tap("memory.add");tap("memory2.manual.option")
        tap("self · preference · " + scope)
        input("memory2.manual.text",value);input("memory2.manual.time","time unknown / 时间不详")
        dismissKeyboard()
        tap("memory2.manual.review")
        text("memory2.review.text",contains:value)
    }
    private func save(_ value: String,scope: String,expected: String? = nil) {
        reviewSave(value,scope:scope)
        tap("memory2.manual.confirm");text("memory2.save.status",contains:expected ?? localized("Saved.","已保存"))
        back()
    }
    private func call(_ path: String) async throws -> Data {
        #if G2C_M4_DEVICE_ACCEPTANCE
        let (data,response) = try await deviceSession.data(path)
        #else
        let (data,response) = try await URLSession.shared.data(from:XCTUnwrap(URL(string:control + path)))
        #endif
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        return data
    }
    private func openTravelItem() async throws {
        tap("Memory");tap("memory2.items.open");tap("memory2.items.read")
        let ids = try JSONDecoder().decode([String:String].self,from:await call("/items"))
        tap("memory2.item." + (try XCTUnwrap(ids["travel"])));tap("memory2.detail.read")
    }
    private func management(_ operation: String,expected: String) {
        tap("memory2.manage.review." + operation)
        tap("memory2.manage.confirm");text("memory2.manage.status",contains:expected)
    }
    private func reconcileAll() async throws {
        tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let originals = try JSONDecoder().decode([String:[String]].self,from:await call("/originals"))
        for original in try XCTUnwrap(originals["saves"]) {tap("memory2.original.query." + original);text("memory2.save.status",contains:"Saved.")}
        for original in try XCTUnwrap(originals["management"]) {tap("memory2.action.query." + original);text("memory2.manage.status",contains:"Original receipt verified")}
        back()
    }
    private func completedMessages(_ count: Int,expected: String = "Travel A quiet room / 本次A安静房间") async throws {
        let data = try await call("/wait-completed?count=" + String(count))
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
    private func launch(_ fixture: Fixture,restore: Bool,release: Bool = false,legacy: Bool = false) async throws {
        app?.terminate();app = XCUIApplication(bundleIdentifier:"space.go2china.typed-memory.acceptance")
        app.launchArguments = ["-cj.ui.language.v1",chinese ? "zh-Hans" : "en"]
        #if G2C_M4_DEVICE_ACCEPTANCE
        let accountsJSON = "{}"
        #else
        let accountsJSON = restore ? "{}" : String(data:try JSONEncoder().encode(fixture.accounts),encoding:.utf8)!
        #endif
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1",
            "G2C_DEV_API_BASE_URL":fixture.endpoint,"G2C_DEV_ACCOUNTS":accountsJSON,
            "G2C_DEV_TRAVEL_PROFILE":fixture.travel_profile,"G2C_DEV_TYPED_MEMORY_PROFILE":fixture.memory_profile,
            "G2C_DEV_TYPED_MEMORY_URL":fixture.memory_endpoint]
        if legacy {
            for key in ["G2C_DEV_TRAVEL_PROFILE","G2C_DEV_TYPED_MEMORY_PROFILE","G2C_DEV_TYPED_MEMORY_URL"] {app.launchEnvironment.removeValue(forKey:key)}
            app.launchEnvironment["G2C_DEV_MEMORY_PROFILE"] = fixture.legacy_profile
        }
        #if G2C_M4_DEVICE_ACCEPTANCE
        if !restore { try await deviceSession.stageAccounts() }
        app.launchEnvironment.merge(try deviceSession.applicationEnvironment(endpoint: fixture.endpoint,
            injecting: !restore, additionalEndpoints: [fixture.memory_endpoint])) { _, value in value }
        #endif
        app.launch();tap("Memory")
        if release {return}
        tap("memory.account")
        if restore {tap("account.development.restore")}
        else {tap("account.development.signout");tap("account.development.signin.A")}
        text("account.development.status",contains:fixture.subjects["A"]!)
        let ready = app.buttons.matching(identifier:legacy ? "Load groups" : "memory2.items.open").firstMatch
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
    func testTypedGroupsPaged() async throws {
        continueAfterFailure=false;executionTimeAllowance=900
        let f=try await prepare();defer { app?.terminate() };try await launch(f,restore:false)
        tap("memory2.items.open");tap("memory2.items.read")
        text("memory2.items.coverage",contains:"not account-wide totals")
        text("memory2.group.empty.preference",contains:"pages read so far")
        XCTAssertFalse(app.buttons.matching(identifier:"memory2.item.group-21").firstMatch.exists)
        tap("memory2.items.next")
        let last=app.buttons.matching(identifier:"memory2.item.group-21").firstMatch;reveal(last,id:"last.group.record")
        XCTAssertTrue(last.label.contains("SYNTHETIC grouped preference 21"))
        tap("memory2.items.next")
        XCTAssertFalse(app.buttons.matching(identifier:"memory2.items.next").firstMatch.exists)
        let first=app.buttons.matching(identifier:"memory2.item.group-00").firstMatch;reveal(first,id:"first.group.record")
        XCTAssertTrue(first.label.contains("SYNTHETIC grouped fact 0"))
        _ = try await call("/groups-proof")
        var issues=0;continueAfterFailure=true
        try app.performAccessibilityAudit(for:.all) { issue in issues+=1;print("TYPED_GROUPS",issue.detailedDescription,issue.element?.label ?? "unavailable");return false }
        continueAfterFailure=false;XCTAssertEqual(issues,0)
    }
    func testTypedGroupsLateAccount() async throws {
        continueAfterFailure=false;executionTimeAllowance=900
        let f=try await prepare();defer { app?.terminate() };try await launch(f,restore:false)
        tap("memory2.items.open");_ = try await call("/arm-hold");tap("memory2.items.read");_ = try await call("/wait-held")
        back();tap("memory.account");tap("account.development.signin.B")
        text("account.development.status",contains:try XCTUnwrap(f.subjects["B"]))
        _ = try await call("/release-held")
        back();tap("memory2.items.open");tap("memory2.items.read")
        text("memory2.items.status",contains:"No memories found")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","memory2.item.group-")).count,0)
        _ = try await call("/groups-proof")
        var issues=0;continueAfterFailure=true
        try app.performAccessibilityAudit(for:.all) { issue in issues+=1;print("TYPED_GROUPS_LATE",issue.detailedDescription,issue.element?.label ?? "unavailable");return false }
        continueAfterFailure=false;XCTAssertEqual(issues,0)
    }
    func testTypedQuestionsEnglish() async throws { try await questions(large:false) }
    func testTypedQuestionsChineseLargest() async throws { try await questions(large:true) }
    private func questions(large:Bool) async throws {
        continueAfterFailure=false;executionTimeAllowance=900;chinese=large
        let fixture=try await prepare();defer { app?.terminate() }
        try await launch(fixture,restore:false)
        let count=try XCTUnwrap(fixture.question_count);XCTAssertTrue((2...3).contains(count))
        tap("memory2.collection.open");text("memory2.collection.progress",contains:"1/"+String(count))
        for step in 1..<count { tap("memory2.collection.next");text("memory2.collection.progress",contains:String(step+1)+"/"+String(count)) }
        _ = try await call("/collection-no-write")
        tap("memory2.collection.skip")
        XCTAssertTrue(app.tabBars.buttons.matching(identifier:localized("Assistant","助手")).firstMatch.isSelected)
        chooseTravel(fixture.travel_ids[0]);tap("Memory")
        tap("memory2.collection.open")
        for _ in 1..<count { tap("memory2.collection.next") }
        let value="SYNTHETIC questions preference / 问题偏好 e\u{301}"
        tap("memory2.manual.option");tap("self · preference · "+(large ? "Selected travel / 所选旅行" : "Long term / 长期"))
        input("memory2.manual.text",value);input("memory2.manual.time","time unknown / 时间不详");dismissKeyboard()
        tap("memory2.manual.review");text("memory2.review.text",contains:value)
        text("memory2.review.subject",contains:"self · preference")
        text("memory2.review.scope",contains:large ? fixture.travel_ids[0] : "Long-term")
        _ = try await call("/collection-no-write")
        var issues=0;continueAfterFailure=true
        try app.performAccessibilityAudit(for:.all) { issue in issues+=1;print("TYPED_QUESTIONS_REVIEW",issue.detailedDescription,issue.element?.label ?? "unavailable");return false }
        continueAfterFailure=false;XCTAssertEqual(issues,0)
        tap("memory2.manual.confirm");text("memory2.save.status",contains:localized("Saved.","已保存"))
        _ = try await call("/collection-saved")
        back();tap("memory2.items.open");tap("memory2.items.read")
        text("memory2.items.coverage",contains:localized("pages read so far","已读取页面"))
        text("memory2.group.empty.fact",contains:localized("pages read so far","已读取页面"))
        let ids=try JSONDecoder().decode([String:String].self,from:await call("/items"))
        let id=try XCTUnwrap(ids[large ? "travel" : "long_term"])
        let row=app.buttons.matching(identifier:"memory2.item."+id).firstMatch
        reveal(row,id:"memory2.item."+id)
        XCTAssertTrue(row.label.contains(value) && row.label.contains("self") && row.label.contains("preference"),"Actual saved row identity, text and kind must remain readable")
        issues=0;continueAfterFailure=true
        try app.performAccessibilityAudit(for:.all) { issue in issues+=1;print("TYPED_QUESTIONS_GROUPS",issue.detailedDescription,issue.element?.label ?? "unavailable");return false }
        continueAfterFailure=false;XCTAssertEqual(issues,0)
        tap("Assistant");openChat("typed-chat-1");try await ask("Use my saved preference",count:1,expected:value)
    }
    func testUnknownReopenAndLifecycleRecall() async throws {
        continueAfterFailure = false;executionTimeAllowance = 900
        let f = try await prepare();defer {app?.terminate()}
        try await launch(f,restore:false)
        _ = try await call("/arm-loss?kind=save")
        let long = "Unknown original long term / 未知原文 e\u{301}"
        save(long,scope:"Long term / 长期",expected:"Result unknown")
        save("Must not bypass original save",scope:"Long term / 长期",expected:"Query the earlier original operation first")
        try await launch(f,restore:true);try await reconcileAll()
        tap("Assistant");chooseTravel(f.travel_ids[0]);tap("Memory")
        let current = "Recovered travel current / 恢复本次原文"
        save(current,scope:"Selected travel / 所选旅行")
        try await openTravelItem()
        _ = try await call("/arm-loss?kind=management")
        management("pause",expected:"Result unknown")
        back();back()
        save("Must not bypass original management",scope:"Long term / 长期",expected:"Query the earlier original operation first")
        try await launch(f,restore:true);try await reconcileAll()
        tap("Assistant");chooseTravel(f.travel_ids[0]);openChat("typed-chat-1")
        try await ask("Recall with the current item paused",count:1,expected:long)
        try await openTravelItem();text("memory2.detail.status",contains:"Disabled")
        management("resume",expected:"Original receipt verified")
        tap("memory2.detail.read");text("memory2.detail.status",contains:"Active")
        tap("Assistant");try await ask("Recall after explicitly resuming",count:2,expected:current)
        tap("Memory");tap("memory2.detail.read");management("stopUse",expected:"Original receipt verified")
        tap("memory2.detail.read");text("memory2.detail.status",contains:"Stopped using")
        text("memory2.detail.text",contains:current)
        tap("Assistant");try await ask("Recall after stopping use; keep the original history",count:3,expected:long)
    }
    func testSwitchAccountAfterActualCommit() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600
        let f = try await prepare();defer {app?.terminate()}
        try await launch(f,restore:false)
        _ = try await call("/arm-hold")
        reviewSave("Account A delayed original / A迟到原文",scope:"Long term / 长期")
        tap("memory2.manual.confirm");_ = try await call("/wait-held")
        back();tap("memory.account");tap("account.development.signin.B")
        text("account.development.status",contains:try XCTUnwrap(f.subjects["B"]))
        _ = try await call("/release-held")
        tap("Memory")
        if app.staticTexts.matching(identifier:"account.development.status").firstMatch.exists {back()}
        tap("memory2.items.open");tap("memory2.items.read")
        text("memory2.items.status",contains:"No memories found")
        XCTAssertFalse(app.staticTexts.matching(identifier:"memory2.save.status").firstMatch.exists)
        XCTAssertFalse(app.staticTexts.matching(identifier:"Account A delayed original / A迟到原文").firstMatch.exists)
        back();tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let originals = try JSONDecoder().decode([String:[String]].self,from:await call("/originals"))
        for original in try XCTUnwrap(originals["saves"]) {XCTAssertFalse(app.buttons.matching(identifier:"memory2.original.query." + original).firstMatch.exists)}
    }
    func testReleaseTypedFlagsRemainClosed() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600
        let f = try await prepare();defer {app?.terminate()}
        try await launch(f,restore:false,release:true)
        XCTAssertFalse(app.buttons.matching(identifier:"account.development.signin.A").firstMatch.exists)
        XCTAssertFalse(app.buttons.matching(identifier:"memory2.items.open").firstMatch.exists)
        tap("memory.add")
        XCTAssertFalse(app.buttons.matching(identifier:"memory2.manual.review").firstMatch.exists)
        XCTAssertFalse(app.buttons.matching(identifier:"memory.manual.save").firstMatch.exists)
        back();tap("Assistant")
        XCTAssertFalse(app.buttons.matching(identifier:"assistant.travelContext").firstMatch.exists)
        input("assistant.draft","Release typed flags must not authorize sending");dismissKeyboard()
        XCTAssertFalse(app.buttons.matching(identifier:"assistant.send").firstMatch.exists)
        let unavailable = app.buttons.matching(identifier:"Send — service not connected").firstMatch
        XCTAssertTrue(unavailable.exists);XCTAssertFalse(unavailable.isEnabled)
    }
    func testLegacyUnknownCannotBypassTypedMode() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600
        let f = try await prepare();defer {app?.terminate()}
        try await launch(f,restore:false,legacy:true)
        _ = try await call("/arm-loss?kind=legacy")
        let original = "Legacy unresolved original / 旧版未知原文 e\u{301}"
        tap("memory.add");tap("memory.manual.scope");tap("self · preference · Long term / 长期")
        input("memory.manual.text",original);input("memory.manual.time","time unknown / 时间不详");dismissKeyboard()
        tap("memory.manual.save");text("memory.save.status",contains:"Result unknown")
        // Preserve the same signed account, main endpoint, encrypted directory
        // and key. Change only the explicitly configured consumer wire mode.
        try await launch(f,restore:true)
        tap("memory.add");tap("memory2.manual.option");tap("self · preference · Long term / 长期")
        input("memory2.manual.text","Must not bypass legacy unknown");input("memory2.manual.time","unknown");dismissKeyboard()
        tap("memory2.manual.review");text("memory2.manual.error",contains:"earlier originals could not be verified")
        XCTAssertFalse(app.buttons.matching(identifier:"memory2.manual.confirm").firstMatch.exists)
        back();tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let originals = try JSONDecoder().decode([String:[String]].self,from:await call("/originals"))
        let old = try XCTUnwrap(originals["legacy"]);XCTAssertEqual(old.count,1)
        tap("memory2.legacy.query." + (try XCTUnwrap(old.first)));text("memory2.save.status",contains:"Saved.")
        back();tap("Assistant");chooseTravel(f.travel_ids[0]);tap("Memory")
        save("Fresh typed save after legacy reconciliation / 核实后新保存",scope:"Selected travel / 所选旅行")
        // The frozen canonical long-term slot is shared by V1/V2. A second
        // active entry cannot be treated as a successful new namespace.
        save("Duplicate active long-term / 保留原条目",scope:"Long term / 长期",expected:"Result unknown")
        tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let all = try JSONDecoder().decode([String:[String]].self,from:await call("/originals"))
        let typed = try XCTUnwrap(all["saves"]);XCTAssertEqual(typed.count,2)
        tap("memory2.original.query." + (try XCTUnwrap(typed.last)))
        text("memory2.save.status",contains:"Original receipt not observed")
        back();tap("Assistant");chooseTravel(f.travel_ids[1]);tap("Memory")
        save("Must not bypass unobserved typed original",scope:"Selected travel / 所选旅行",expected:"Query the earlier original operation first")
    }
    func testRealConflictKeepsOriginalAndAllowsFreshSave() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600
        let f = try await prepare();defer {app?.terminate()}
        try await launch(f,restore:false)
        save("Conflict source / 并发原条目",scope:"Long term / 长期")
        tap("memory2.items.open");tap("memory2.items.read")
        let ids = try JSONDecoder().decode([String:String].self,from:await call("/items"))
        tap("memory2.item." + (try XCTUnwrap(ids["long_term"])));tap("memory2.detail.read")
        let originalText = "Conflicting original edit / 冲突原文 e\u{301}"
        input("memory2.edit.text",originalText);dismissKeyboard()
        tap("memory2.manage.review.edit");text("memory2.manage.review.after",contains:originalText)
        _ = try await call("/concurrent-pause")
        tap("memory2.manage.confirm");text("memory2.manage.status",contains:"original action was rejected")
        try await launch(f,restore:true)
        tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let originals = try JSONDecoder().decode([String:[String]].self,from:await call("/originals"))
        for id in try XCTUnwrap(originals["saves"]) {tap("memory2.original.query." + id);text("memory2.save.status",contains:"Saved.")}
        let actions = try XCTUnwrap(originals["management"]);XCTAssertEqual(actions.count,1)
        let id = try XCTUnwrap(actions.first)
        text("memory2.original.action.text." + id,contains:originalText)
        let retained = app.staticTexts.matching(identifier:"memory2.original.action.text." + id).firstMatch
        XCTAssertEqual(Array(retained.label.utf8),Array(originalText.utf8))
        XCTAssertFalse(app.textFields.matching(identifier:"memory2.original.action.text." + id).firstMatch.exists)
        tap("memory2.action.query." + id);text("memory2.manage.status",contains:"original action was rejected")
        var issues = 0;continueAfterFailure = true
        try app.performAccessibilityAudit(for:.all) {issue in issues += 1;print("TYPED_CONFLICT_ORIGINAL",issue.detailedDescription,issue.element?.label ?? "unavailable");return false}
        continueAfterFailure = false;XCTAssertEqual(issues,0)
        back();save("Fresh after actual conflict / 明确冲突后新保存",scope:"Long term / 长期")
    }
    func testTypedUnknownCannotReactivateLegacyWriter() async throws {
        continueAfterFailure = false;executionTimeAllowance = 900
        let f = try await prepare();defer {app?.terminate()}
        try await launch(f,restore:false,legacy:true)
        tap("memory.add");tap("memory.manual.scope");tap("self · legacy.read · Long term / 长期")
        input("memory.manual.text","Original legacy read remains available / 保留旧只读回执")
        input("memory.manual.time","time unknown");dismissKeyboard()
        tap("memory.manual.save");text("memory.save.status",contains:"Saved.")
        try await launch(f,restore:true)
        tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let old = try JSONDecoder().decode([String:[String]].self,from:await call("/originals"))
        let legacy = try XCTUnwrap(old["legacy"]);XCTAssertEqual(legacy.count,1)
        tap("memory2.legacy.query." + (try XCTUnwrap(legacy.first)));text("memory2.save.status",contains:"Saved.");back()
        tap("Assistant");chooseTravel(f.travel_ids[0]);tap("Memory")
        _ = try await call("/arm-loss?kind=save")
        save("Typed unknown cannot downgrade / 新版未知不能回退写入",scope:"Selected travel / 所选旅行",expected:"Result unknown")
        try await launch(f,restore:true,legacy:true)
        tap("memory.add")
        let saveButton = app.buttons.matching(identifier:"memory.manual.save").firstMatch
        XCTAssertTrue(saveButton.waitForExistence(timeout:10));XCTAssertFalse(saveButton.isEnabled)
        tap("Read original operations");tap("Query this original operation")
        text("memory.original.status",contains:"Saved.")
        try await launch(f,restore:true)
        tap("memory.manage.openOriginals");tap("memory2.originals.read")
        tap("memory2.legacy.query." + (try XCTUnwrap(legacy.first)));text("memory2.save.status",contains:"Saved.")
        let data = try await call("/originals"),originals = try JSONDecoder().decode([String:[String]].self,from:data)
        let typed = try XCTUnwrap(originals["saves"]);XCTAssertEqual(typed.count,1)
        tap("memory2.original.query." + (try XCTUnwrap(typed.first)));text("memory2.save.status",contains:"Saved.")
        back();save("Fresh compatible typed action / 兼容入口新保存",scope:"Long term / 长期")
        try await launch(f,restore:true,legacy:true);tap("memory.add")
        let knownSaveButton = app.buttons.matching(identifier:"memory.manual.save").firstMatch
        XCTAssertTrue(knownSaveButton.waitForExistence(timeout:10));XCTAssertFalse(knownSaveButton.isEnabled)
    }
    func testChineseLargeSaveReadAndRecall() async throws {
        continueAfterFailure = false;executionTimeAllowance = 600;chinese = true
        let fixture = try await prepare();defer {app?.terminate()}
        try await launch(fixture,restore:false)
        save("中文长期偏好 / 长期 e\u{301}",scope:"Long term / 长期")
        tap("Assistant");chooseTravel(fixture.travel_ids[0]);tap("Memory")
        let value = "中文本次偏好 / 安静房间 e\u{301}"
        save(value,scope:"Selected travel / 所选旅行")
        tap("memory2.items.open");tap("memory2.items.read")
        let data = try await call("/items")
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
        try await launch(fixture,restore:false)
        save("Typed long-term tea / 新长期 e\u{301}",scope:"Long term / 长期")
        tap("Assistant");tap("assistant.travelContext");tap("travel.selection." + fixture.travel_ids[0])
        text("travel.selection.status",contains:fixture.travel_ids[0]);tap("assistant.panel.done");tap("Memory")
        save("Travel A quiet room / 本次A安静房间",scope:"Selected travel / 所选旅行")
        tap("memory2.items.open");tap("memory2.items.read")
        let data = try await call("/items")
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
        try await launch(fixture,restore:true)
        tap("Assistant");chooseTravel(fixture.travel_ids[0]);openChat("typed-chat-3")
        try await ask("Use current memory after restarting the App",count:4,expected:updated)
        chooseTravel(fixture.travel_ids[1])
        try await ask("Use only this other travel and long-term memory",count:5,expected:"Typed long-term tea / 新长期 e\u{301}")
        // The reopened client must query original save/lifecycle receipts before
        // a fresh save; navigating away does not erase verified completions.
        tap("Memory");tap("memory.manage.openOriginals");tap("memory2.originals.read")
        let originalData = try await call("/originals")
        let originals = try JSONDecoder().decode([String:[String]].self,from:originalData)
        for original in try XCTUnwrap(originals["saves"]) {tap("memory2.original.query." + original);text("memory2.save.status",contains:"Saved.")}
        for original in try XCTUnwrap(originals["management"]) {tap("memory2.action.query." + original);text("memory2.manage.status",contains:"Original receipt verified")}
        back()
        save("Travel B separate value / B独立值",scope:"Selected travel / 所选旅行")
        tap("Assistant");try await ask("Use this travel's own updated preference",count:6,expected:"Travel B separate value / B独立值")
    }
}
