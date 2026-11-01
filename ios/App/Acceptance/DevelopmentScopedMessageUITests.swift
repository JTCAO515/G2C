import XCTest
import Foundation

@MainActor final class DevelopmentScopedMessageUITests:XCTestCase {
    private let bundle="space.go2china.scoped.acceptance"
    private let control="__FIXTURE_URL__"
    private var app:XCUIApplication!
    private struct Fixture:Decodable {
        let case_id,endpoint,conversation,namespace:String
        let accounts,subjects:[String:String]
        let formal_trips:[FormalTrip]
        let manual_profile:Bool?
        let manual_only:Bool?
        let needs_planning:Bool?
    }
    private struct FormalTrip:Decodable {
        let id,title,content_sha256:String
        let version:Int
        let item_ids:[String]
    }
    private struct Proof:Decodable {
        let runtime_role:String
        let messages,posts,model_calls,registered_operations,formal_version,formal_count,pending_proposals,forbidden_writes:Int
        let status,draft_outcome,trip_id,content_sha256,namespace:String
        let needs_version:Int
        let item_ids:[String]
        let day:String?
        let memory_long,memory_current,memory_other:Bool
    }
    private func call(_ path:String,caseID:String) async throws -> Data {
        var url=URLComponents(string:control+path)!
        url.queryItems=[.init(name:"case",value:caseID)]
        let (data,response)=try await URLSession.shared.data(from:XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200)
        return data
    }
    private func prepare(_ name:String) async throws -> Fixture {
        continueAfterFailure=false;executionTimeAllowance=900
        return try JSONDecoder().decode(Fixture.self,from:await call("/prepare",caseID:name))
    }
    private func textElement(_ id:String) -> XCUIElement {
        let text=app.staticTexts.matching(identifier:id).firstMatch
        if text.exists { return text }
        let view=app.textViews.matching(identifier:id).firstMatch
        if view.exists { return view }
        return app.otherElements.matching(identifier:id).firstMatch
    }
    private func visible(_ lookup:()->XCUIElement,id:String) -> XCUIElement {
        for attempt in 0..<70 {
            let element=lookup(),navigation=app.navigationBars.firstMatch
            var top=navigation.exists ? navigation.frame.maxY+4 : app.frame.minY+60
            var bottom=navigation.exists ? app.frame.maxY-24 : app.tabBars.firstMatch.frame.minY
            let tabBar=app.tabBars.firstMatch
            if tabBar.exists && tabBar.isHittable { bottom=min(bottom,tabBar.frame.minY) }
            let header=app.otherElements.matching(identifier:"assistant.header").firstMatch
            let composer=app.otherElements.matching(identifier:"assistant.composer").firstMatch
            if !navigation.exists && !["assistant.draft","assistant.send","assistant.intent"].contains(id) && header.exists && composer.exists {
                top=max(top,header.frame.maxY+8);bottom=min(bottom,composer.frame.minY)
            }
            let frame=element.exists ? element.frame : .zero
            if element.exists && element.isHittable && frame.midY>top && frame.midY<bottom { return element }
            let located = !frame.isEmpty && frame.minY.isFinite && frame.maxY.isFinite
            let down=located ? frame.midY<=top : attempt>=35
            let middle=(top+bottom)/2,step=min(150,(bottom-top)*0.35)
            let start=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? -step : step)))
            let end=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? step : -step)))
            start.press(forDuration:0.05,thenDragTo:end)
        }
        capture("not-visible-"+id)
        let tree=XCTAttachment(string:app.debugDescription);tree.name="not-visible-tree-"+id;tree.lifetime = .keepAlways;add(tree)
        XCTFail("Expected visible control: "+id);return lookup()
    }
    private func tap(_ id:String) {
        let target:XCUIElement
        if ["Assistant","助手","Memory","记忆","Trips","行程"].contains(id) { target=app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if ["assistant.panel.done","timeline.done","trip.manual.keyboard.done"].contains(id) { target=app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else if id=="assistant.history" { target=app.buttons.matching(identifier:id).firstMatch }
        else if ["Done","完成"].contains(id) { target=app.toolbars.buttons.matching(identifier:id).firstMatch }
        else { target=visible({app.buttons.matching(identifier:id).firstMatch},id:id) }
        XCTAssertTrue(target.waitForExistence(timeout:15),id)
        let ready=XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == true AND hittable == true AND enabled == true"),object:target)
        let outcome=XCTWaiter.wait(for:[ready],timeout:20)
        if outcome != .completed { capture("not-ready-"+id) }
        XCTAssertEqual(outcome,.completed,id+" enabled="+String(target.isEnabled)+" hittable="+String(target.isHittable))
        if id.hasPrefix("travel.selection.") { print("namespace control",id,"frame",target.frame,"screen",app.frame);capture("before-namespace-tap") }
        if id.hasPrefix("travel.selection.") { target.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap() }
        else { target.tap() }
    }
    private func text(_ id:String,contains expected:String) {
        let target=visible({textElement(id)},id:id)
        let predicate=NSPredicate { _,_ in target.label.contains(expected) || (target.value as? String)?.contains(expected)==true }
        let observed=XCTNSPredicateExpectation(predicate:predicate,object:target)
        let outcome=XCTWaiter.wait(for:[observed],timeout:15)
        if outcome != .completed { capture("unexpected-text-"+id) }
        XCTAssertEqual(outcome,.completed,id+" expected="+expected+" actual="+target.label+" value="+String(describing:target.value))
    }
    private func capture(_ name:String) {
        let attachment=XCTAttachment(screenshot:app.screenshot());attachment.name=name;attachment.lifetime = .keepAlways;add(attachment)
    }
    private func audit(_ name:String) throws {
        var issues=0;continueAfterFailure=true;defer { continueAfterFailure=false }
        try app.performAccessibilityAudit(for:.all) { issue in issues+=1;print(name,issue.detailedDescription,issue.element?.label ?? "unavailable");return false }
        XCTAssertEqual(issues,0)
    }
    private func launch(_ f:Fixture,language:String,large:Bool=false,restore:Bool=false,timezone:String?=nil) throws {
        app?.terminate();app=XCUIApplication(bundleIdentifier:bundle)
        app.launchArguments=["-cj.ui.language.v1",language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment=["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_ACCOUNTS":restore ? "{}" : String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,"G2C_DEV_MESSAGE_PROFILE":"trip-edit-v1",
            "G2C_DEV_NEEDS_PROFILE":"manual-v1","G2C_DEV_NEEDS_ID":"visit",
            "G2C_DEV_TRAVEL_PROFILE":String(data:try JSONSerialization.data(withJSONObject:["version":"app-travel.1","travel_ids":[f.namespace]]),encoding:.utf8)!,
            "G2C_DEV_TYPED_MEMORY_PROFILE":"{\"version\":\"app-memory.2\",\"subjects\":[\"self\"],\"slots\":{\"food\":{\"kind\":\"preference\",\"collection_allowed\":true,\"semantic_resolved\":true},\"pace\":{\"kind\":\"preference\",\"collection_allowed\":true,\"semantic_resolved\":true}},\"extents\":[\"long_term\",\"current\"]}",
            "G2C_DEV_TYPED_MEMORY_URL":f.endpoint]
        if f.manual_profile == true { app.launchEnvironment["G2C_DEV_TRIP_MANUAL_PROFILE"]="manual-v1" }
        if f.manual_only == true {
            for key in ["G2C_DEV_MESSAGE_PROFILE","G2C_DEV_TRAVEL_PROFILE","G2C_DEV_TYPED_MEMORY_PROFILE","G2C_DEV_TYPED_MEMORY_URL"] { app.launchEnvironment.removeValue(forKey:key) }
        }
        if f.needs_planning == true {
            app.launchEnvironment["G2C_DEV_MESSAGE_PROFILE"]="needs-planning-v1"
            for key in ["G2C_DEV_TYPED_MEMORY_PROFILE","G2C_DEV_TYPED_MEMORY_URL"] { app.launchEnvironment.removeValue(forKey:key) }
        }
        if let timezone { app.launchEnvironment["TZ"]=timezone }
        app.launch();XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:15))
        tap(language=="en" ? "Memory" : "记忆");tap("memory.account")
        if restore { tap("account.development.restore") }
        else { tap("account.development.signout");tap("account.development.signin.A") }
        text("account.development.status",contains:try XCTUnwrap(f.subjects["A"]))
        tap(language=="en" ? "Assistant" : "助手")
    }
    private func conversation(_ f:Fixture) {
        tap("assistant.serverHistory");tap("history.loadConversations");tap("history.conversation."+f.conversation);tap("assistant.panel.done")
    }
    private func enter(_ value:String,language:String) {
        let field=visible({
            let multiline=app.textViews.matching(identifier:"assistant.draft").firstMatch
            return multiline.exists ? multiline : app.textFields.matching(identifier:"assistant.draft").firstMatch
        },id:"assistant.draft")
        let enabled=XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true AND hittable == true"),object:field)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:20),.completed,"Current editor must be enabled")
        field.tap();field.typeText(value);XCTAssertEqual(field.value as? String,value)
        let done=app.toolbars.buttons.matching(identifier:language=="en" ? "Done" : "完成").firstMatch
        if done.exists { done.tap() }
    }
    private func replaceManualText(_ id:String,_ value:String) {
        func input() -> XCUIElement {
            let multiline=app.textViews.matching(identifier:id).firstMatch
            return multiline.exists ? multiline : app.textFields.matching(identifier:id).firstMatch
        }
        let field=visible({input()},id:id)
        XCTAssertTrue(field.isEnabled && field.isHittable);field.tap();field.press(forDuration:1.1)
        let selection=app.descendants(matching:.any).matching(NSPredicate(format:"label IN %@",["Select All","全选"])).firstMatch
        XCTAssertTrue(selection.waitForExistence(timeout:5));selection.tap();field.typeText(value)
        XCTAssertEqual(input().value as? String,value);tap("trip.manual.keyboard.done")
    }
    private func scenario(_ name:String,language:String,large:Bool=false,item:Bool=false,switchLanguage:Bool=false,undetermined:Bool=false,decision:String?=nil,ackLoss:Bool=false,invalidation:String?=nil,lateAccount:Bool=false,discoveryUnavailable:Bool=false,fixedReorder:Bool=false) async throws {
        let f=try await prepare(name);defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first)
        try launch(f,language:language,large:large);conversation(f)
        tap(language=="en" ? "Trips" : "行程")
        if f.manual_profile == true { tap("trip.manual.browse") }
        tap("trips.timeline.open");tap("timeline.refresh");tap("timeline.trip."+trip.id)
        text("timeline.record.title",contains:trip.title)
        capture(name+"-formal-source");try audit(name+"-formal-source")
        let chosen=trip.item_ids[item ? 1 : 2]
        if item { tap("timeline.discuss.item."+chosen) }
        else { tap("timeline.discuss.day.2026-11-04|Asia/Shanghai") }
        text("assistant.edit.trip.id",contains:trip.id);text("assistant.edit.trip.version",contains:"2")
        tap("assistant.travelContext");tap("travel.selection."+f.namespace);text("travel.selection.status",contains:f.namespace)
        XCTAssertFalse(app.buttons.matching(identifier:"travel.selection.none").firstMatch.exists)
        tap("assistant.panel.done")
        tap("assistant.edit.needs.open");tap("needs.read")
        text("needs.container.state",contains:language=="en" ? "User-provided details loaded" : "已读取用户提供的条件")
        tap("assistant.panel.done");tap("assistant.edit.needs.choose");tap("assistant.edit.intent.propose")
        text("assistant.edit.needs",contains:"visit");text("assistant.edit.intent",contains:language=="en" ? "request a scoped candidate" : "请求局部候选")
        if item { text("assistant.edit.trip.item",contains:chosen);XCTAssertFalse(app.staticTexts.matching(identifier:"assistant.edit.trip.day").firstMatch.exists) }
        else { text("assistant.edit.trip.day",contains:"2026-11-04") }
        var activeLanguage=language
        if switchLanguage {
            tap("Memory")
            for _ in 0..<3 {
                if app.buttons.matching(identifier:"memory.language").firstMatch.exists { break }
                let back=app.navigationBars.buttons.firstMatch;XCTAssertTrue(back.exists);back.tap()
            }
            tap("memory.language");tap("简体中文");tap("助手");activeLanguage="zh-Hans"
            text("assistant.edit.trip.id",contains:trip.id);text("assistant.edit.trip.version",contains:"2")
            text("assistant.edit.needs",contains:"visit");text("assistant.edit.intent",contains:"请求局部候选")
        }
        capture(name+"-explicit-original-choices");try audit(name+"-choices")
        enter(activeLanguage=="en" ? "SYNTHETIC Make selected item lighter" : "SYNTHETIC 本次轻松一点",language:activeLanguage);tap("assistant.send")
        let proof=try JSONDecoder().decode(Proof.self,from:await call("/wait-completed",caseID:name))
        XCTAssertEqual(proof.runtime_role,"cj_m1_runtime");XCTAssertEqual(proof.messages,1);XCTAssertEqual(proof.posts,1)
        if undetermined {
            XCTAssertEqual(proof.model_calls,0);XCTAssertEqual(proof.registered_operations,0);XCTAssertEqual(proof.pending_proposals,0)
            XCTAssertEqual(proof.draft_outcome,"validation_failed")
        } else {
            XCTAssertEqual(proof.model_calls,1);XCTAssertEqual(proof.registered_operations,1);XCTAssertEqual(proof.pending_proposals,1)
            XCTAssertEqual(proof.draft_outcome,"published")
        }
        XCTAssertEqual(proof.formal_count,1);XCTAssertEqual(proof.formal_version,2);XCTAssertEqual(proof.forbidden_writes,0)
        XCTAssertEqual(proof.status,"completed")
        XCTAssertEqual(proof.trip_id,trip.id);XCTAssertEqual(proof.content_sha256,trip.content_sha256);XCTAssertEqual(proof.namespace,f.namespace);XCTAssertEqual(proof.needs_version,1)
        XCTAssertEqual(proof.item_ids,item ? [chosen] : []);XCTAssertEqual(proof.day,item ? nil : "2026-11-04")
        if !undetermined { XCTAssertTrue(proof.memory_long);XCTAssertTrue(proof.memory_current) }
        XCTAssertFalse(proof.memory_other)
        tap("run.snapshot.read");text("run.display.status",contains:activeLanguage=="en" ? "Completed" : "已完成")
        XCTAssertFalse(textElement("run.display.text").exists, "Scoped model wire output is not a user-facing answer")
        XCTAssertFalse(textElement("run.stream.text").exists, "Scoped model wire progress is not a user-facing answer")
        if undetermined { text("run.draft.status",contains:activeLanguage=="en" ? "no candidate published" : "未发布候选") }
        else { text("run.draft.status",contains:activeLanguage=="en" ? "not a saved trip" : "尚非正式行程") }
        capture(name+"-published-not-adopted");try audit(name+"-original-run")
        if discoveryUnavailable {
            _ = try await call("/invalidate-candidate",caseID:name)
            for _ in 0..<2 {
                tap("scoped.discover");text("scoped.activity",contains:"Protected candidate unavailable")
                XCTAssertFalse(textElement("scoped.discovery.state").exists)
                XCTAssertFalse(textElement("scoped.after."+chosen).exists)
                XCTAssertFalse(app.buttons.matching(identifier:"scoped.accept").firstMatch.exists)
                XCTAssertFalse(app.buttons.matching(identifier:"scoped.reject").firstMatch.exists)
            }
            _ = try await call("/discovery-refusal-proof",caseID:name)
            capture(name+"-failed-read-no-action-no-model");try audit(name+"-discovery-refusal")
        }
        if lateAccount {
            tap("scoped.discover");_ = try await call("/wait-discovery",caseID:name)
            tap("Memory")
            if !app.buttons.matching(identifier:"account.development.signin.B").firstMatch.exists { tap("memory.account") }
            tap("account.development.signin.B")
            text("account.development.status",contains:try XCTUnwrap(f.subjects["B"]))
            _ = try await call("/release-discovery",caseID:name)
            tap("Assistant")
            text("scoped.activity",contains:"Choose an accepted original message")
            XCTAssertFalse(textElement("scoped.discovery.state").exists)
            XCTAssertFalse(textElement("scoped.after."+chosen).exists)
            XCTAssertFalse(app.buttons.matching(identifier:"scoped.accept").firstMatch.exists)
            XCTAssertFalse(app.buttons.matching(identifier:"scoped.reject").firstMatch.exists)
            _ = try await call("/late-proof",caseID:name)
            capture(name+"-late-original-withheld-from-B");try audit(name+"-late-account")
        }
        if let decision {
            tap("scoped.discover");text("scoped.discovery.state",contains:activeLanguage=="en" ? "Original candidate" : "原候选")
            text("scoped.feasibility",contains:"UNKNOWN")
            if fixedReorder {
                let fixed=visible({app.staticTexts.matching(NSPredicate(format:"label CONTAINS %@","固定状态：是")).firstMatch},id:"fixed.original")
                XCTAssertTrue(fixed.exists && fixed.isHittable)
            }
            text("scoped.before."+chosen,contains:fixedReorder ? "Great Wall" : "Jingshan Park")
            text("scoped.after."+chosen,contains:"本次轻松一点")
            if fixedReorder {
                text("scoped.order."+chosen,contains:"3 → 4")
                text("scoped.order."+trip.item_ids[3],contains:"4 → 3")
            }
            capture(name+"-original-diff-unknown");try audit(name+"-diff")
            if invalidation != nil { _ = try await call("/invalidate-candidate",caseID:name) }
            tap("scoped."+decision)
            if ackLoss || invalidation != nil {
                text("scoped.activity",contains:invalidation=="conflict" ? "conflict" : "UNKNOWN")
                XCTAssertFalse(app.buttons.matching(identifier:"scoped.accept").firstMatch.isEnabled)
                XCTAssertFalse(app.buttons.matching(identifier:"scoped.reject").firstMatch.isEnabled)
                XCTAssertFalse(textElement("scoped.receipt").exists)
            } else { text("scoped.receipt",contains:activeLanguage=="en" ? "confirmed" : "已确认") }
            if decision=="accept" && !ackLoss && invalidation==nil {
                text("scoped.receipt.version",contains:"3");text("scoped.formal.version",contains:trip.id+" · 3")
                text("scoped.formal.item."+chosen,contains:"本次轻松一点")
            }
            _ = try await call("/decision-proof",caseID:name)
            capture(name+"-original-decision");try audit(name+"-decision")
            // Relaunch supplies no token. Explicit restore, original journal and GET only.
            try launch(f,language:activeLanguage,restore:true)
            tap("scoped.originals")
            let original=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","scoped.query.")).firstMatch},id:"scoped.originals")
            XCTAssertTrue(original.exists && original.isHittable && original.isEnabled);original.tap()
            if let invalidation { text("scoped.activity",contains:invalidation=="conflict" ? "conflict" : "UNKNOWN") }
            else { text("scoped.receipt",contains:activeLanguage=="en" ? "confirmed" : "已确认") }
            if ackLoss { text("scoped.formal.version",contains:trip.id+" · 3") }
            _ = try await call("/decision-proof",caseID:name)
            capture(name+"-restart-original-receipt");try audit(name+"-restart")
        }

    }
    func testNeedsManualFixedRoundTrip() async throws {
        let name="testNeedsManualFixedRoundTrip",f=try await prepare(name)
        defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first)
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id);tap("trip.manual.needs.read")
        func changeFixed(_ value:Bool) {
            tap("trip.manual.edit.open")
            let item=visible({app.descendants(matching:.any).matching(identifier:"trip.manual.item.open.b").firstMatch},id:"trip.manual.item.open.b")
            XCTAssertTrue(item.isHittable && item.isEnabled);item.tap()
            let selected=visible({app.switches.matching(identifier:"trip.manual.selected.b").firstMatch},id:"trip.manual.selected.b")
            XCTAssertTrue(selected.isEnabled);selected.tap()
            tap(value ? "trip.manual.fixed.true.b" : "trip.manual.fixed.false.b")
            tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Exact diff prepared")
            text("trip.manual.after.fixed.b",contains:value ? "Explicitly fixed" : "Explicitly unlocked")
            text("trip.manual.after.fixed.a",contains:"Explicitly fixed")
            tap("trip.manual.save")
        }
        changeFixed(true);text("trip.manual.receipt",contains:"2")
        _ = try await call("/manual-fixed-on-proof",caseID:name)
        tap("trip.manual.replaceBasis");text("trip.manual.record.fixed.b",contains:"Explicitly fixed")
        changeFixed(false);text("trip.manual.receipt",contains:"3")
        tap("trip.manual.current");text("trip.manual.current.version",contains:"3")
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-fixed-roundtrip");try audit(name+"-roundtrip")
        try launch(f,language:"zh-Hans",restore:true)
        tap("行程");tap("trip.manual.originals.read")
        let original=visible({app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open.s:")).firstMatch},id:"manual.fixed.original")
        XCTAssertTrue(original.isEnabled && original.isHittable);original.tap()
        let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query.s:")).firstMatch},id:"manual.fixed.query")
        XCTAssertTrue(query.isEnabled && query.isHittable);query.tap()
        text("trip.manual.original.result",contains:"原回执已核对")
        tap("trip.structured.refresh");tap("trip.structured.item."+trip.id)
        text("trip.manual.record.fixed.a",contains:"明确固定")
        text("trip.manual.record.fixed.b",contains:"明确未固定")
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-fixed-readback");try audit(name+"-restart")
    }
    func testNeedsPlanningPrefix() async throws { try await planningScenario("testNeedsPlanningPrefix") }
    func testNeedsPlanningAccept() async throws { try await planningScenario("testNeedsPlanningAccept",decision:"accept") }
    func testNeedsPlanningReject() async throws { try await planningScenario("testNeedsPlanningReject",decision:"reject") }
    func testNeedsPlanningACKLoss() async throws { try await planningScenario("testNeedsPlanningACKLoss",decision:"accept",ackLoss:true) }
    func testNeedsPlanningDiscoveryUnavailable() async throws { try await planningScenario("testNeedsPlanningDiscoveryUnavailable",discoveryUnavailable:true) }
    func testNeedsPlanningStaleAccept() async throws { try await planningScenario("testNeedsPlanningStaleAccept",decision:"accept",invalidation:"needs") }
    func testNeedsPlanningConflict() async throws { try await planningScenario("testNeedsPlanningConflict",decision:"accept",invalidation:"compete") }
    func testNeedsPlanningLateAccount() async throws { try await planningScenario("testNeedsPlanningLateAccount",lateAccount:true) }
    func testNeedsPlanningInterruptedAccept() async throws { try await planningScenario("testNeedsPlanningInterruptedAccept",decision:"accept",interrupted:true) }
    func testNeedsPlanningManualComposition() async throws { try await planningScenario("testNeedsPlanningManualComposition",decision:"accept",composition:true) }
    func testNeedsPlanningOriginalsLargest() async throws {
        let name="testNeedsPlanningOriginalsLargest",f=try await prepare(name)
        defer { app?.terminate() }
        try launch(f,language:"zh-Hans",large:true)
        tap("planning.originals");text("planning.activity",contains:"请选择已接受的原消息")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","planning.query.")).count,0)
        _ = try await call("/prefix-not-sent",caseID:name)
        capture(name+"-visible-originals");try audit(name+"-largest")
    }
    func testNeedsPlanningCurrentFixedAccept() async throws { try await planningScenario("testNeedsPlanningCurrentFixedAccept",decision:"accept",composition:true,currentDecision:"accept") }
    func testNeedsPlanningCurrentFixedACKLoss() async throws { try await planningScenario("testNeedsPlanningCurrentFixedACKLoss",decision:"accept",composition:true,currentDecision:"accept") }
    func testNeedsPlanningCurrentUnlockedReject() async throws { try await planningScenario("testNeedsPlanningCurrentUnlockedReject",decision:"accept",composition:true,currentDecision:"reject") }
    private func planningScenario(_ name:String,decision:String?=nil,ackLoss:Bool=false,invalidation:String?=nil,discoveryUnavailable:Bool=false,lateAccount:Bool=false,interrupted:Bool=false,composition:Bool=false,currentDecision:String?=nil) async throws {
        let f=try await prepare(name)
        defer { app?.terminate() }
        XCTAssertEqual(f.needs_planning,true)
        try launch(f,language:"en");conversation(f)
        tap("assistant.travelContext");tap("travel.selection."+f.namespace);tap("assistant.panel.done")
        func setPlanningIntent(_ enabled:Bool) {
            let toggle=visible({app.switches.matching(identifier:"assistant.intent").firstMatch},id:"assistant.intent")
            XCTAssertTrue(toggle.isEnabled && toggle.isHittable)
            XCTAssertEqual(toggle.value as? String,enabled ? "0" : "1")
            toggle.coordinate(withNormalizedOffset:CGVector(dx:0.95,dy:0.5)).tap()
            let changed=XCTNSPredicateExpectation(predicate:NSPredicate(format:"value == %@",enabled ? "1" : "0"),object:toggle)
            XCTAssertEqual(XCTWaiter.wait(for:[changed],timeout:5),.completed)
        }
        setPlanningIntent(true)
        enter("SYNTHETIC Plan using my explicit saved requirements / 使用已保存需求",language:"en")
        XCTAssertFalse(app.buttons.matching(identifier:"assistant.send").firstMatch.isEnabled)
        _ = try await call("/prefix-not-sent",caseID:name)
        setPlanningIntent(false)
        tap("assistant.needs");tap("needs.read");text("needs.container.state",contains:"User-provided details loaded");tap("assistant.panel.done")
        tap("assistant.travelContext");tap("travel.selection.none");tap("assistant.panel.done")
        setPlanningIntent(true)
        XCTAssertFalse(app.buttons.matching(identifier:"assistant.send").firstMatch.isEnabled)
        _ = try await call("/prefix-not-sent",caseID:name)
        tap("assistant.travelContext");tap("travel.selection."+f.namespace);text("travel.selection.status",contains:f.namespace);tap("assistant.panel.done")
        tap("assistant.send");_ = try await call("/manual-save-proof",caseID:name)
        tap("run.snapshot.read");text("run.display.status",contains:"Completed")
        text("run.draft.status",contains:"Draft candidate recorded; not a saved trip")
        XCTAssertFalse(app.buttons.matching(identifier:"scoped.accept").firstMatch.exists)
        capture(name+"-original-planning-run");try audit(name+"-published")
        tap("Memory")
        for _ in 0..<3 {
            if app.buttons.matching(identifier:"memory.language").firstMatch.exists { break }
            let back=app.navigationBars.buttons.firstMatch;XCTAssertTrue(back.exists);back.tap()
        }
        tap("memory.language");tap("简体中文");tap("助手")
        text("run.display.status",contains:"已完成");text("run.draft.status",contains:"已记录草稿候选，尚非正式行程")
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-same-original-Chinese");try audit(name+"-Chinese")
        if discoveryUnavailable {
            _ = try await call("/invalidate-planning-needs",caseID:name)
            for _ in 0..<2 { tap("planning.discover");text("planning.activity",contains:"原读取不可用") }
            XCTAssertFalse(app.buttons.matching(identifier:"planning.accept").firstMatch.exists)
            _ = try await call("/planning-no-decision-proof",caseID:name)
            capture(name+"-read-refused-no-write");try audit(name+"-refused")
        }
        if lateAccount {
            tap("planning.discover");_ = try await call("/wait-planning-response",caseID:name)
            tap("记忆")
            if !app.buttons.matching(identifier:"account.development.signin.B").firstMatch.exists {
                for _ in 0..<3 {
                    if app.buttons.matching(identifier:"memory.account").firstMatch.exists { break }
                    let back=app.navigationBars.buttons.firstMatch;XCTAssertTrue(back.exists);back.tap()
                }
                tap("memory.account")
            }
            tap("account.development.signin.B");text("account.development.status",contains:try XCTUnwrap(f.subjects["B"]))
            _ = try await call("/release-planning-response",caseID:name)
            tap("助手");text("planning.activity",contains:"请选择已接受的原消息")
            XCTAssertFalse(textElement("planning.proposal.title").exists)
            XCTAssertFalse(app.buttons.matching(identifier:"planning.accept").firstMatch.exists)
            XCTAssertFalse(app.buttons.matching(identifier:"planning.discover").firstMatch.isEnabled)
            tap("planning.originals");XCTAssertEqual(app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","planning.query.")).count,0)
            _ = try await call("/planning-no-decision-proof",caseID:name)
            capture(name+"-B-withholds-late-A");try audit(name+"-late")
        }
        if let decision {
            tap("planning.discover");text("planning.discovery.state",contains:"原规划候选已记录")
            text("planning.needs",contains:"visit");text("planning.namespace",contains:f.namespace)
            text("planning.proposal.title",contains:"本地合成来源行程")
            text("planning.proposal.fixed.a",contains:"明确固定")
            capture(name+"-actual-original-candidate");try audit(name+"-candidate")
            if invalidation=="needs" { _ = try await call("/invalidate-planning-needs",caseID:name) }
            if invalidation=="compete" { _ = try await call("/compete-planning",caseID:name) }
            tap("planning."+decision)
            if interrupted {
                _ = try await call("/wait-planning-response",caseID:name)
                app.terminate();XCTAssertEqual(app.state,.notRunning)
                _ = try await call("/release-planning-response",caseID:name)
            } else if invalidation=="compete" {
                text("planning.activity",contains:"冲突");XCTAssertFalse(textElement("planning.receipt").exists)
            } else if ackLoss || invalidation=="needs" {
                text("planning.activity",contains:"UNKNOWN")
                XCTAssertFalse(app.buttons.matching(identifier:"planning.accept").firstMatch.isEnabled)
                XCTAssertFalse(app.buttons.matching(identifier:"planning.reject").firstMatch.isEnabled)
                XCTAssertFalse(textElement("planning.receipt").exists)
            } else {
                text("planning.receipt",contains:decision=="accept" ? "原采用动作已确认" : "原拒绝动作已确认")
                if decision=="accept" { text("planning.receipt.version",contains:"1");text("planning.formal.version",contains:" · 1") }
                else { XCTAssertFalse(textElement("planning.formal.version").exists) }
            }
            _ = try await call("/planning-decision-proof",caseID:name)
            if !interrupted { capture(name+"-original-decision");try audit(name+"-decision") }
            try launch(f,language:"en",restore:true)
            tap("planning.originals")
            let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","planning.query.")).firstMatch},id:"planning.original.query")
            XCTAssertTrue(query.isEnabled && query.isHittable);query.tap()
            if let invalidation {
                text("planning.activity",contains:invalidation=="compete" ? "Conflict" : "UNKNOWN")
                XCTAssertFalse(textElement("planning.receipt").exists)
                XCTAssertFalse(textElement("planning.formal.version").exists)
            } else {
                text("planning.receipt",contains:decision=="accept" ? "Original acceptance confirmed" : "Original rejection confirmed")
                if decision=="accept" { text("planning.receipt.version",contains:"1");text("planning.formal.version",contains:" · 1") }
                else { XCTAssertFalse(textElement("planning.formal.version").exists) }
            }
            XCTAssertFalse(app.buttons.matching(identifier:"planning.accept").firstMatch.exists)
            _ = try await call("/planning-decision-proof",caseID:name)
            capture(name+"-restart-original-only");try audit(name+"-restart")
            if composition {
                struct FormalIdentity:Decodable { let trip_id:String }
                let identity=try JSONDecoder().decode(FormalIdentity.self,from:await call("/planning-decision-proof",caseID:name))
                let input="SYNTHETIC manual after App adoption / 采用后手改"
                tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+identity.trip_id)
                tap("trip.manual.needs.read");tap("trip.manual.edit.open")
                let selected=visible({app.switches.matching(identifier:"trip.manual.title.selected").firstMatch},id:"trip.manual.title.selected")
                XCTAssertTrue(selected.isEnabled && selected.isHittable);selected.tap();replaceManualText("trip.manual.title.value",input)
                tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Exact diff prepared");text("trip.manual.after.title",contains:input)
                tap("trip.manual.save");text("trip.manual.receipt",contains:"2")
                tap("trip.manual.current");text("trip.manual.current.version",contains:"2")
                _ = try await call("/planning-composition-proof",caseID:name)
                capture(name+"-actual-manual-save");try audit(name+"-manual")
                try launch(f,language:"zh-Hans",restore:true)
                tap("planning.originals")
                let historical=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","planning.query.")).firstMatch},id:"planning.historical.query")
                XCTAssertTrue(historical.isEnabled && historical.isHittable);historical.tap()
                text("planning.receipt.version",contains:"1");text("planning.formal.version",contains:" · 2")
                text("planning.formal.title",contains:input)
                XCTAssertFalse(app.buttons.matching(identifier:"planning.accept").firstMatch.exists)
                _ = try await call("/planning-composition-proof",caseID:name)
                capture(name+"-old-receipt-current-manual-version");try audit(name+"-historical")
                if let currentDecision { try await currentPlanningAfterManual(f,name:name,tripID:identity.trip_id,decision:currentDecision) }
            }
        }
    }
    private func currentPlanningAfterManual(_ f:Fixture,name:String,tripID:String,decision:String) async throws {
        try launch(f,language:"en",restore:true)
        let sourceVersion=decision=="reject" ? 5 : 3
        func beginBEdit(replaceBasis:Bool) {
            if replaceBasis { tap("trip.manual.replaceBasis") }
            tap("trip.manual.needs.read");tap("trip.manual.edit.open")
            let item=visible({app.descendants(matching:.any).matching(identifier:"trip.manual.item.open.b").firstMatch},id:"trip.manual.item.open.b")
            XCTAssertTrue(item.isEnabled && item.isHittable);item.tap()
            let selected=visible({app.switches.matching(identifier:"trip.manual.selected.b").firstMatch},id:"trip.manual.selected.b")
            XCTAssertTrue(selected.isEnabled && selected.isHittable);selected.tap();XCTAssertEqual(selected.value as? String,"1")
        }
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+tripID)
        beginBEdit(replaceBasis:false);tap("trip.manual.fixed.true.b")
        tap("trip.manual.prepare");text("trip.manual.issue",contains:"Reconcile retained original actions before another write")
        text("trip.manual.fixed.input.b",contains:"Selected change: fixed")
        _ = try await call("/current-planning-blocked",caseID:name)
        tap("trip.manual.originals.read")
        for (stage,expected) in [("p:","Original preparation verified"),("s:","Original receipt verified")] {
            let row=visible({app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open."+stage)).firstMatch},id:"manual.current.original."+stage)
            XCTAssertTrue(row.isEnabled && row.isHittable);row.tap()
            let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query."+stage)).firstMatch},id:"manual.current.query."+stage)
            XCTAssertTrue(query.isEnabled && query.isHittable);query.tap();text("trip.manual.original.result",contains:expected)
        }
        text("trip.manual.original.result",contains:" · 2");text("trip.manual.fixed.input.b",contains:"Selected change: fixed")
        tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Exact diff prepared");tap("trip.manual.save");text("trip.manual.receipt",contains:"3")
        tap("trip.manual.current");text("trip.manual.current.version",contains:"3")
        if decision=="reject" {
            beginBEdit(replaceBasis:true);tap("trip.manual.fixed.false.b")
            tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Exact diff prepared");tap("trip.manual.save");text("trip.manual.receipt",contains:"4")
            tap("trip.manual.current");text("trip.manual.current.version",contains:"4")
            beginBEdit(replaceBasis:true)
            let textChange=visible({app.switches.matching(identifier:"trip.manual.text.selected.b").firstMatch},id:"trip.manual.text.selected.b")
            XCTAssertTrue(textChange.isEnabled && textChange.isHittable);textChange.tap()
            replaceManualText("trip.manual.text.value.b","SYNTHETIC current replan edit / 后续规划手改")
            let schedule=visible({app.switches.matching(identifier:"trip.manual.schedule.selected.b").firstMatch},id:"trip.manual.schedule.selected.b")
            XCTAssertTrue(schedule.isEnabled && schedule.isHittable);schedule.tap()
            replaceManualText("trip.manual.start.b.time.value","11:15");replaceManualText("trip.manual.end.b.time.value","12:15")
            tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Exact diff prepared")
            text("trip.manual.after.item.b",contains:"SYNTHETIC current replan edit / 后续规划手改")
            text("trip.manual.after.schedule.b",contains:"11:15");text("trip.manual.after.schedule.b",contains:"12:15")
            tap("trip.manual.save");text("trip.manual.receipt",contains:"5")
            tap("trip.manual.current");text("trip.manual.current.version",contains:"5")
        }
        _ = try await call("/current-planning-source",caseID:name)
        tap("Assistant");conversation(f)
        tap("assistant.travelContext");tap("travel.selection."+f.namespace);tap("assistant.panel.done")
        tap("assistant.needs");tap("needs.read");text("needs.container.state",contains:"User-provided details loaded");tap("assistant.panel.done")
        let intent=visible({app.switches.matching(identifier:"assistant.intent").firstMatch},id:"assistant.intent")
        XCTAssertEqual(intent.value as? String,"0");intent.coordinate(withNormalizedOffset:CGVector(dx:0.95,dy:0.5)).tap()
        XCTAssertEqual(intent.value as? String,"1")
        enter("SYNTHETIC Replan from my current edited and fixed Trip / 按已手改和固定的行程重新规划",language:"en")
        tap("assistant.send");_ = try await call("/current-planning-published",caseID:name)
        tap("run.snapshot.read");text("run.display.status",contains:"Completed")
        tap("planning.discover");text("planning.discovery.state",contains:"Original planning candidate recorded")
        text("planning.context",contains:tripID);text("planning.context",contains:" · "+String(sourceVersion))
        let ackLoss=name.hasSuffix("ACKLoss")
        tap("planning."+decision)
        if ackLoss {
            text("planning.activity",contains:"UNKNOWN")
            XCTAssertFalse(textElement("planning.receipt").exists)
            XCTAssertFalse(textElement("planning.formal.version").exists)
            let accept=app.buttons.matching(identifier:"planning.accept").firstMatch
            XCTAssertFalse(accept.exists && accept.isEnabled)
        } else { text("planning.receipt",contains:decision=="accept" ? "Original acceptance confirmed" : "Original rejection confirmed") }
        struct CurrentProof:Decodable { let original_action_id,proposed_trip_id,source_content_sha256:String }
        let proof=try JSONDecoder().decode(CurrentProof.self,from:await call("/current-planning-proof",caseID:name))
        text("planning.context.hash",contains:proof.source_content_sha256)
        if decision=="accept" && !ackLoss { text("planning.formal.version",contains:proof.proposed_trip_id+" · 1") }
        else { XCTAssertFalse(textElement("planning.formal.version").exists) }
        capture(name+"-source2-decision");try audit(name+"-source2")
        try launch(f,language:"zh-Hans",large:decision=="reject",restore:true);tap("planning.originals");tap("planning.query."+proof.original_action_id)
        text("planning.receipt",contains:decision=="accept" ? "原采用动作已确认" : "原拒绝动作已确认")
        text("planning.context",contains:tripID);text("planning.context",contains:" · "+String(sourceVersion))
        if decision=="accept" { text("planning.formal.version",contains:proof.proposed_trip_id+" · 1") }
        _ = try await call("/current-planning-proof",caseID:name)
        capture(name+"-source2-original-recovery");try audit(name+"-source2-restart")
    }
    func testNeedsManualCanonicalFixedRefusal() async throws {
        try await manualRejectedPreparation("testNeedsManualCanonicalFixedRefusal",invalidWindow:false)
    }
    func testNeedsManualInvalidWindow() async throws {
        try await manualRejectedPreparation("testNeedsManualInvalidWindow",invalidWindow:true)
    }
    private func manualRejectedPreparation(_ name:String,invalidWindow:Bool) async throws {
        let f=try await prepare(name)
        defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first)
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id);tap("trip.manual.needs.read");tap("trip.manual.edit.open")
        let itemID=invalidWindow ? "b" : "a"
        let item=visible({app.descendants(matching:.any).matching(identifier:"trip.manual.item.open."+itemID).firstMatch},id:"trip.manual.item.open."+itemID)
        XCTAssertTrue(item.isEnabled && item.isHittable);item.tap()
        let selected=visible({app.switches.matching(identifier:"trip.manual.selected."+itemID).firstMatch},id:"trip.manual.selected."+itemID)
        XCTAssertTrue(selected.isEnabled && selected.isHittable);selected.tap()
        if invalidWindow {
            let schedule=visible({app.switches.matching(identifier:"trip.manual.schedule.selected.b").firstMatch},id:"trip.manual.schedule.selected.b")
            XCTAssertTrue(schedule.isEnabled && schedule.isHittable);schedule.tap()
            replaceManualText("trip.manual.start.b.time.value","11:15")
            replaceManualText("trip.manual.end.b.time.value","10:30")
        } else {
            tap("trip.manual.fixed.false.a")
            text("trip.manual.fixed.input.a",contains:"Selected change: unlocked")
        }
        tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Original request refused")
        text("trip.manual.refusal",contains:"Save conflict");text("trip.manual.refusal",contains:"409")
        if invalidWindow {
            for (id,value) in [("trip.manual.start.b.time.value","11:15"),("trip.manual.end.b.time.value","10:30")] {
                let field=visible({app.textFields.matching(identifier:id).firstMatch},id:id)
                XCTAssertEqual(field.value as? String,value)
            }
        } else { text("trip.manual.fixed.input.a",contains:"Selected change: unlocked") }
        XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.save").firstMatch.isEnabled)
        XCTAssertFalse(textElement("trip.manual.receipt").exists)
        tap("trip.manual.current");text("trip.manual.current.version",contains:"1")
        text("trip.manual.refusal",contains:"Save conflict")
        capture(name+"-canonical-protection");try audit(name+"-refused")
        try launch(f,language:"zh-Hans",restore:true)
        tap("行程");tap("trip.manual.originals.read")
        let original=visible({app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open.p:")).firstMatch},id:"manual.fixed.refused.original")
        XCTAssertTrue(original.isEnabled && original.isHittable);original.tap()
        let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query.p:")).firstMatch},id:"manual.fixed.refused.query")
        XCTAssertTrue(query.isEnabled && query.isHittable);query.tap();text("trip.manual.original.result",contains:"原拒绝已核对")
        text("trip.manual.original.result",contains:"TRIP_CONFLICT")
        XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.save").firstMatch.exists)
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-original-refusal");try audit(name+"-restart")
    }
    func testNeedsManualPrepareCancellation() async throws {
        let name="testNeedsManualPrepareCancellation",f=try await prepare(name)
        defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first),input="SYNTHETIC cancelled manual / 停止等待保留"
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id);tap("trip.manual.needs.read");tap("trip.manual.edit.open")
        let selected=visible({app.switches.matching(identifier:"trip.manual.title.selected").firstMatch},id:"trip.manual.title.selected")
        XCTAssertTrue(selected.isEnabled && selected.isHittable);selected.tap();replaceManualText("trip.manual.title.value",input)
        tap("trip.manual.prepare");_ = try await call("/wait-manual-preparation",caseID:name)
        tap("trip.manual.stop");text("trip.manual.editor.state",contains:"Result unknown")
        XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.save").firstMatch.isEnabled)
        XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.prepare").firstMatch.isEnabled)
        _ = try await call("/release-manual-preparation",caseID:name)
        text("trip.manual.editor.state",contains:"Result unknown")
        XCTAssertFalse(textElement("trip.manual.receipt").exists)
        capture(name+"-cancelled");try audit(name+"-cancelled")
        try launch(f,language:"zh-Hans",restore:true)
        tap("行程");tap("trip.manual.originals.read")
        let original=visible({app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open.p:")).firstMatch},id:"manual.cancel.original")
        XCTAssertTrue(original.isEnabled && original.isHittable);original.tap()
        let raw=visible({app.textViews.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.input.p:")).firstMatch},id:"manual.cancel.input")
        XCTAssertTrue((raw.value as? String)?.contains(input)==true || raw.label.contains(input))
        let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query.p:")).firstMatch},id:"manual.cancel.query")
        XCTAssertTrue(query.isEnabled && query.isHittable);query.tap();text("trip.manual.original.result",contains:"原准备记录已核对")
        XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.save").firstMatch.exists)
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-original-only");try audit(name+"-restart")
    }
    func testNeedsManualLateAccount() async throws {
        let name="testNeedsManualLateAccount",f=try await prepare(name)
        defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first)
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id);tap("trip.manual.needs.read");tap("trip.manual.edit.open")
        let selected=visible({app.switches.matching(identifier:"trip.manual.title.selected").firstMatch},id:"trip.manual.title.selected")
        XCTAssertTrue(selected.isEnabled && selected.isHittable);selected.tap()
        replaceManualText("trip.manual.title.value","SYNTHETIC private A pending / A私有修改")
        tap("trip.manual.prepare");_ = try await call("/wait-manual-preparation",caseID:name)
        tap("Memory")
        if !app.buttons.matching(identifier:"account.development.signin.B").firstMatch.exists { tap("memory.account") }
        tap("account.development.signin.B");text("account.development.status",contains:try XCTUnwrap(f.subjects["B"]))
        _ = try await call("/release-manual-preparation",caseID:name)
        tap("Trips");tap("trip.structured.refresh");text("trip.structured.state",contains:"Formal record read")
        XCTAssertFalse(app.buttons.matching(identifier:"trip.structured.item."+trip.id).firstMatch.exists)
        XCTAssertFalse(textElement("trip.manual.basis").exists)
        XCTAssertFalse(textElement("trip.manual.editor.state").exists)
        XCTAssertFalse(textElement("trip.manual.after.title").exists)
        XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.save").firstMatch.exists)
        tap("trip.manual.originals.read")
        XCTAssertEqual(app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open.")).count,0)
        XCTAssertEqual(app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query.")).count,0)
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-B-after-late-A");try audit(name+"-account")
    }
    func testNeedsManualTimeTextSave() async throws {
        let name="testNeedsManualTimeTextSave",f=try await prepare(name)
        defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first),input="SYNTHETIC explicit time and text / 明确修改"
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id);tap("trip.manual.needs.read");tap("trip.manual.edit.open")
        let item=visible({app.descendants(matching:.any).matching(identifier:"trip.manual.item.open.b").firstMatch},id:"trip.manual.item.open.b")
        XCTAssertTrue(item.isHittable);item.tap()
        for id in ["trip.manual.selected.b","trip.manual.text.selected.b"] {
            let selected=visible({app.switches.matching(identifier:id).firstMatch},id:id)
            XCTAssertTrue(selected.isEnabled && selected.isHittable);selected.tap()
        }
        replaceManualText("trip.manual.text.value.b",input)
        let schedule=visible({app.switches.matching(identifier:"trip.manual.schedule.selected.b").firstMatch},id:"trip.manual.schedule.selected.b")
        XCTAssertTrue(schedule.isEnabled);schedule.tap()
        replaceManualText("trip.manual.start.b.time.value","11:15")
        replaceManualText("trip.manual.end.b.time.value","12:15")
        tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Exact diff prepared")
        text("trip.manual.after.item.b",contains:input)
        text("trip.manual.after.schedule.b",contains:"11:15")
        text("trip.manual.after.schedule.b",contains:"12:15")
        text("trip.manual.after.fixed.a",contains:"Explicitly fixed")
        tap("trip.manual.save");text("trip.manual.receipt",contains:"2")
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-saved");try audit(name+"-saved")
        try launch(f,language:"zh-Hans",restore:true)
        tap("行程");tap("trip.manual.originals.read")
        let original=visible({app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open.s:")).firstMatch},id:"manual.time.original")
        XCTAssertTrue(original.isEnabled && original.isHittable);original.tap()
        let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query.s:")).firstMatch},id:"manual.time.query")
        XCTAssertTrue(query.isEnabled && query.isHittable);query.tap();text("trip.manual.original.result",contains:"原回执已核对")
        tap("trip.structured.refresh");tap("trip.structured.item."+trip.id)
        text("trip.manual.record.item.b",contains:input)
        text("trip.manual.record.schedule.b",contains:"11:15")
        text("trip.manual.record.schedule.b",contains:"12:15")
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-restart");try audit(name+"-restart")
    }
    func testNeedsManualTitleSave() async throws { try await manualTitleSave("testNeedsManualTitleSave",ackLoss:false) }
    func testNeedsManualSaveACKLoss() async throws { try await manualTitleSave("testNeedsManualSaveACKLoss",ackLoss:true) }
    func testNeedsManualSaveConflict() async throws { try await manualTitleSave("testNeedsManualSaveConflict",ackLoss:false,conflict:true) }
    private func manualTitleSave(_ name:String,ackLoss:Bool,conflict:Bool=false) async throws {
        let f=try await prepare(name)
        defer { app?.terminate() }
        XCTAssertEqual(f.manual_profile,true);XCTAssertEqual(f.manual_only,true)
        let trip=try XCTUnwrap(f.formal_trips.first),input="SYNTHETIC manual saved title / 手动保存标题"
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id)
        tap("trip.manual.needs.read");tap("trip.manual.edit.open")
        let selected=visible({app.switches.matching(identifier:"trip.manual.title.selected").firstMatch},id:"trip.manual.title.selected")
        XCTAssertTrue(selected.isEnabled);selected.tap()
        func titleField() -> XCUIElement {
            let multiline=app.textViews.matching(identifier:"trip.manual.title.value").firstMatch
            return multiline.exists ? multiline : app.textFields.matching(identifier:"trip.manual.title.value").firstMatch
        }
        let field=visible({titleField()},id:"trip.manual.title.value")
        XCTAssertEqual(try XCTUnwrap(field.value as? String),trip.title)
        replaceManualText("trip.manual.title.value",input)
        tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Exact diff prepared")
        text("trip.manual.after.title",contains:input)
        if conflict { _ = try await call("/manual-compete",caseID:name) }
        tap("trip.manual.save")
        if conflict {
            text("trip.manual.editor.state",contains:"Original request refused")
            text("trip.manual.refusal",contains:"Save conflict")
            text("trip.manual.refusal",contains:"409")
            XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.save").firstMatch.isEnabled)
            XCTAssertFalse(textElement("trip.manual.receipt").exists)
            text("trip.manual.after.title",contains:input)
        } else if ackLoss {
            text("trip.manual.editor.state",contains:"Result unknown")
            XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.save").firstMatch.isEnabled)
            XCTAssertFalse(textElement("trip.manual.receipt").exists)
        } else { text("trip.manual.receipt",contains:"2") }
        tap("trip.manual.current");text("trip.manual.current.version",contains:"2")
        if ackLoss { text("trip.manual.editor.state",contains:"Result unknown");XCTAssertFalse(textElement("trip.manual.receipt").exists) }
        if conflict { text("trip.manual.refusal",contains:"Save conflict");XCTAssertFalse(textElement("trip.manual.receipt").exists) }
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-saved-original");try audit(name+"-saved")
        try launch(f,language:"zh-Hans",restore:true)
        tap("行程");tap("trip.manual.originals.read")
        let row=visible({app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open.s:")).firstMatch},id:"manual.saved.original")
        XCTAssertTrue(row.isEnabled && row.isHittable);row.tap()
        let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query.s:")).firstMatch},id:"manual.saved.query")
        XCTAssertTrue(query.isEnabled && query.isHittable);query.tap()
        text("trip.manual.original.result",contains:conflict ? "原拒绝已核对" : "原回执已核对")
        _ = try await call("/manual-save-proof",caseID:name)
        capture(name+"-restart-original-only");try audit(name+"-restart")
    }
    func testManualProtectedPrepareUnknownRestart() async throws {
        let name="testManualProtectedPrepareUnknownRestart", f=try await prepare(name)
        defer { app?.terminate() }
        XCTAssertEqual(f.manual_profile,true)
        let trip=try XCTUnwrap(f.formal_trips.first), input="SYNTHETIC retained title / 原输入保留"
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id);tap("trip.manual.edit.open")
        let selected=visible({app.switches.matching(identifier:"trip.manual.title.selected").firstMatch},id:"trip.manual.title.selected")
        XCTAssertTrue(selected.isEnabled);selected.tap()
        func titleField() -> XCUIElement {
            let multiline=app.textViews.matching(identifier:"trip.manual.title.value").firstMatch
            return multiline.exists ? multiline : app.textFields.matching(identifier:"trip.manual.title.value").firstMatch
        }
        let field=visible({titleField()},id:"trip.manual.title.value")
        XCTAssertEqual(try XCTUnwrap(field.value as? String),trip.title)
        field.tap();field.press(forDuration:1.1)
        let selection=app.descendants(matching:.any).matching(NSPredicate(format:"label IN %@",["Select All","全选"])).firstMatch
        if !selection.waitForExistence(timeout:5) {
            capture("manual-title-edit-menu-unavailable")
            let tree=XCTAttachment(string:app.debugDescription);tree.name="manual-title-edit-menu-tree";tree.lifetime = .keepAlways;add(tree)
            XCTFail("Expected the native Select All action");return
        }
        selection.tap();field.typeText(input)
        XCTAssertEqual(titleField().value as? String,input);tap("trip.manual.keyboard.done")
        tap("trip.manual.prepare");text("trip.manual.editor.state",contains:"Result unknown")
        XCTAssertEqual(titleField().value as? String,input)
        let save=app.buttons.matching(identifier:"trip.manual.save").firstMatch
        XCTAssertTrue(save.exists,"The retained editor explains the blocked save")
        XCTAssertFalse(save.isEnabled,"Unknown preparation cannot be saved")
        XCTAssertFalse(app.buttons.matching(identifier:"trip.manual.prepare").firstMatch.isEnabled)
        func queryRetained() {
            tap("trip.manual.originals.read")
            let row=visible({app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.open.")).firstMatch},id:"manual.original.open")
            XCTAssertTrue(row.isEnabled && row.isHittable);row.tap()
            let raw=visible({
                let predicate=NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.input.")
                let selectable=app.textViews.matching(predicate).firstMatch
                return selectable.exists ? selectable : app.staticTexts.matching(predicate).firstMatch
            },id:"manual.original.input")
            XCTAssertTrue(raw.label.contains(input) || (raw.value as? String)?.contains(input)==true)
            let query=visible({app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@","trip.manual.original.query.")).firstMatch},id:"manual.original.query")
            XCTAssertTrue(query.isEnabled && query.isHittable);query.tap()
        }
        queryRetained();text("trip.manual.original.result",contains:"remains unknown")
        capture(name+"-original-input-retained");try audit(name+"-unknown")
        try launch(f,language:"zh-Hans",restore:true)
        tap("行程");queryRetained();text("trip.manual.original.result",contains:"仍未知")
        _ = try await call("/manual-unknown-proof",caseID:name)
        capture(name+"-restart-original-only");try audit(name+"-restart")
    }
    func testScopedFixedReorderChineseLargest() async throws { try await scenario("testScopedFixedReorderChineseLargest",language:"zh-Hans",large:true,decision:"accept",fixedReorder:true) }
    func testScopedCandidateDiscoveryUnavailable() async throws { try await scenario("testScopedCandidateDiscoveryUnavailable",language:"en",item:true,discoveryUnavailable:true) }
    func testScopedCandidateLateAccount() async throws { try await scenario("testScopedCandidateLateAccount",language:"en",item:true,lateAccount:true) }
    func testScopedCandidateStaleAcceptance() async throws { try await scenario("testScopedCandidateStaleAcceptance",language:"en",item:true,decision:"accept",invalidation:"stale") }
    func testScopedCandidateConflict() async throws { try await scenario("testScopedCandidateConflict",language:"en",item:true,decision:"reject",invalidation:"conflict") }
    func testScopedCandidateWithdrawal() async throws { try await scenario("testScopedCandidateWithdrawal",language:"en",item:true,decision:"accept",invalidation:"withdrawal") }
    func testScopedCandidateACKLoss() async throws { try await scenario("testScopedCandidateACKLoss",language:"en",item:true,decision:"accept",ackLoss:true) }
    func testScopedCandidateAccept() async throws { try await scenario("testScopedCandidateAccept",language:"en",item:true,switchLanguage:true,decision:"accept") }
    func testScopedCandidateReject() async throws { try await scenario("testScopedCandidateReject",language:"en",item:true,decision:"reject") }
    func testScopedItemAndLanguageSwitch() async throws { try await scenario("testScopedItemAndLanguageSwitch",language:"en",item:true,switchLanguage:true) }
    func testScopedDayChineseLargest() async throws { try await scenario("testScopedDayChineseLargest",language:"zh-Hans",large:true) }
    func testScopedUndeterminedDayWithoutModel() async throws { try await scenario("testScopedUndeterminedDayWithoutModel",language:"en",undetermined:true) }
}
