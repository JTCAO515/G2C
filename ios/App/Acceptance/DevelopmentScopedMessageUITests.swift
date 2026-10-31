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
        capture("not-visible-"+id);XCTFail("Expected visible control: "+id);return lookup()
    }
    private func tap(_ id:String) {
        let target:XCUIElement
        if ["Assistant","助手","Memory","记忆","Trips","行程"].contains(id) { target=app.tabBars.buttons.matching(identifier:id).firstMatch }
        else if ["assistant.panel.done","timeline.done"].contains(id) { target=app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else if id=="assistant.history" { target=app.buttons.matching(identifier:id).firstMatch }
        else if ["Done","完成"].contains(id) { target=app.toolbars.buttons.matching(identifier:id).firstMatch }
        else { target=visible({app.buttons.matching(identifier:id).firstMatch},id:id) }
        XCTAssertTrue(target.waitForExistence(timeout:15),id)
        let ready=XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == true AND hittable == true AND enabled == true"),object:target)
        let outcome=XCTWaiter.wait(for:[ready],timeout:20)
        if outcome != .completed { capture("not-ready-"+id) }
        XCTAssertEqual(outcome,.completed,id+" enabled="+String(target.isEnabled)+" hittable="+String(target.isHittable))
        target.tap()
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
    private func scenario(_ name:String,language:String,large:Bool=false,item:Bool=false,switchLanguage:Bool=false) async throws {
        let f=try await prepare(name);defer { app?.terminate() }
        let trip=try XCTUnwrap(f.formal_trips.first)
        try launch(f,language:language,large:large);conversation(f)
        tap(language=="en" ? "Trips" : "行程");tap("trips.timeline.open");tap("timeline.refresh");tap("timeline.trip."+trip.id)
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
        XCTAssertEqual(proof.model_calls,1);XCTAssertEqual(proof.registered_operations,1);XCTAssertEqual(proof.pending_proposals,1)
        XCTAssertEqual(proof.formal_count,1);XCTAssertEqual(proof.formal_version,2);XCTAssertEqual(proof.forbidden_writes,0)
        XCTAssertEqual(proof.status,"completed");XCTAssertEqual(proof.draft_outcome,"published")
        XCTAssertEqual(proof.trip_id,trip.id);XCTAssertEqual(proof.content_sha256,trip.content_sha256);XCTAssertEqual(proof.namespace,f.namespace);XCTAssertEqual(proof.needs_version,1)
        XCTAssertEqual(proof.item_ids,item ? [chosen] : []);XCTAssertEqual(proof.day,item ? nil : "2026-11-04")
        XCTAssertTrue(proof.memory_long);XCTAssertTrue(proof.memory_current);XCTAssertFalse(proof.memory_other)
        tap("run.snapshot.read");text("run.display.status",contains:activeLanguage=="en" ? "Completed" : "已完成")
        text("run.draft.status",contains:activeLanguage=="en" ? "not a saved trip" : "尚非正式行程")
        capture(name+"-published-not-adopted");try audit(name+"-original-run")
    }
    func testScopedItemAndLanguageSwitch() async throws { try await scenario("testScopedItemAndLanguageSwitch",language:"en",item:true,switchLanguage:true) }
    func testScopedDayChineseLargest() async throws { try await scenario("testScopedDayChineseLargest",language:"zh-Hans",large:true) }
}
