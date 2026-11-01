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
            if !navigation.exists && !["assistant.draft","assistant.send"].contains(id) && header.exists && composer.exists {
                top=max(top,header.frame.maxY+8);bottom=min(bottom,composer.frame.minY)
            }
            let frame=element.exists ? element.frame : .zero
            if element.exists && element.isHittable && frame.midY>top && frame.midY<bottom { return element }
            let located = !frame.isEmpty && frame.minY.isFinite && frame.maxY.isFinite
            let down=located ? frame.midY<=top : attempt>=35
            let middle=(top+bottom)/2,step=min(150,(bottom-top)*0.35)
            let start=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width-6,dy:middle+(down ? -step : step)))
            let end=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width-6,dy:middle+(down ? step : -step)))
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
    func testNeedsManualLateAccount() async throws {
        let name="testNeedsManualLateAccount",f=try await prepare(name)
        defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first)
        try launch(f,language:"en")
        tap("Trips");tap("trip.structured.refresh");tap("trip.structured.item."+trip.id);tap("trip.manual.needs.read");tap("trip.manual.edit.open")
        let selected=visible({app.switches.matching(identifier:"trip.manual.title.selected").firstMatch},id:"trip.manual.title.selected")
        XCTAssertTrue(selected.isEnabled && selected.isHittable);selected.tap()
        let field=visible({
            let multiline=self.app.textViews.matching(identifier:"trip.manual.title.value").firstMatch
            return multiline.exists ? multiline : self.app.textFields.matching(identifier:"trip.manual.title.value").firstMatch
        },id:"trip.manual.title.value")
        field.tap();field.press(forDuration:1.1)
        let selectAll=app.descendants(matching:.any).matching(NSPredicate(format:"label IN %@",["Select All","全选"])).firstMatch
        XCTAssertTrue(selectAll.waitForExistence(timeout:5));selectAll.tap();field.typeText("SYNTHETIC private A pending / A私有修改")
        XCTAssertEqual(field.value as? String,"SYNTHETIC private A pending / A私有修改");tap("trip.manual.keyboard.done")
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
        func replace(_ id:String,_ value:String) {
            let field=visible({
                let multiline=self.app.textViews.matching(identifier:id).firstMatch
                return multiline.exists ? multiline : self.app.textFields.matching(identifier:id).firstMatch
            },id:id)
            XCTAssertTrue(field.isEnabled);field.tap();field.press(forDuration:1.1)
            let selection=app.descendants(matching:.any).matching(NSPredicate(format:"label IN %@",["Select All","全选"])).firstMatch
            XCTAssertTrue(selection.waitForExistence(timeout:5));selection.tap();field.typeText(value)
            XCTAssertEqual(field.value as? String,value);tap("trip.manual.keyboard.done")
        }
        replace("trip.manual.text.value.b",input)
        let schedule=visible({app.switches.matching(identifier:"trip.manual.schedule.selected.b").firstMatch},id:"trip.manual.schedule.selected.b")
        XCTAssertTrue(schedule.isEnabled);schedule.tap()
        replace("trip.manual.start.b.time.value","11:15")
        replace("trip.manual.end.b.time.value","12:15")
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
        field.tap();field.press(forDuration:1.1)
        let selection=app.descendants(matching:.any).matching(NSPredicate(format:"label IN %@",["Select All","全选"])).firstMatch
        XCTAssertTrue(selection.waitForExistence(timeout:5));selection.tap();field.typeText(input)
        XCTAssertEqual(titleField().value as? String,input);tap("trip.manual.keyboard.done")
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
