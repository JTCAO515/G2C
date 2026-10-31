import XCTest
import Foundation

@MainActor final class DevelopmentTripDiscussionUITests:XCTestCase {
    private let bundle="space.go2china.discussions.acceptance"
    private let control="__FIXTURE_URL__"
    private var app:XCUIApplication!
    private struct Fixture:Decodable {
        let case_id,endpoint,conversation:String
        let accounts,subjects:[String:String]
    }
    private struct Proof:Decodable {
        let runtime_role:String
        let pending,messages,posts,model_calls,memory_items,forbidden_writes,registered_operations:Int
        let status:String?
        let text:String
        let upgrade_refused:Bool
        let post_statuses:[Int]
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
        else if id=="assistant.panel.done" { target=app.navigationBars.buttons.matching(identifier:id).firstMatch }
        else if ["Done","完成"].contains(id) { target=app.toolbars.buttons.matching(identifier:id).firstMatch }
        else { target=visible({app.buttons.matching(identifier:id).firstMatch},id:id) }
        XCTAssertTrue(target.waitForExistence(timeout:15),id)
        let ready=XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == true AND hittable == true AND enabled == true"),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[ready],timeout:20),.completed,id)
        target.tap()
    }
    private func text(_ id:String,contains expected:String) {
        let target=visible({textElement(id)},id:id)
        let predicate=NSPredicate { _,_ in target.label.contains(expected) || (target.value as? String)?.contains(expected)==true }
        let expected=expectation(for:predicate,evaluatedWith:target)
        wait(for:[expected],timeout:15)
    }
    private func capture(_ name:String) {
        let attachment=XCTAttachment(screenshot:app.screenshot());attachment.name=name;attachment.lifetime = .keepAlways;add(attachment)
    }
    private func audit(_ name:String) throws {
        var issues=0;continueAfterFailure=true;defer { continueAfterFailure=false }
        try app.performAccessibilityAudit(for:.all) { issue in issues+=1;print(name,issue.detailedDescription,issue.element?.label ?? "unavailable");return false }
        XCTAssertEqual(issues,0)
    }
    private func launch(_ f:Fixture,language:String,large:Bool=false) throws {
        app?.terminate();app=XCUIApplication(bundleIdentifier:bundle)
        app.launchArguments=["-cj.ui.language.v1",language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment=["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!,"G2C_DEV_MESSAGE_PROFILE":"trip-discussion-v1"]
        app.launch();XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:15))
        tap(language=="en" ? "Memory" : "记忆");tap("memory.account");tap("account.development.signout");tap("account.development.signin.A")
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
        field.tap();field.typeText(value);XCTAssertEqual(field.value as? String,value)
        let done=app.toolbars.buttons.matching(identifier:language=="en" ? "Done" : "完成").firstMatch
        if done.exists { done.tap() }
    }
    private func unbound(_ name:String,language:String,large:Bool=false) async throws {
        let f=try await prepare(name);defer { app?.terminate() }
        try launch(f,language:language,large:large);conversation(f)
        text("assistant.trip.choice",contains:language=="en" ? "Choose a Trip" : "请选择行程或明确不绑定")
        text("assistant.trip.noAutomatic",contains:language=="en" ? "No latest Trip" : "不会自动选择最近行程")
        tap("assistant.trip.none")
        text("assistant.trip.choice",contains:language=="en" ? "Explicitly no formal Trip" : "已明确不绑定正式行程")
        XCTAssertFalse(app.switches.matching(identifier:"assistant.intent").firstMatch.exists)
        enter(language=="en" ? "SYNTHETIC which Trip is this?" : "SYNTHETIC 这是哪一份行程？",language:language)
        tap("assistant.send")
        let proof=try JSONDecoder().decode(Proof.self,from:await call("/wait-completed",caseID:name))
        XCTAssertEqual(proof.runtime_role,"cj_m1_runtime");XCTAssertEqual(proof.pending,0)
        XCTAssertEqual(proof.messages,1);XCTAssertEqual(proof.posts,1);XCTAssertEqual(proof.model_calls,1);XCTAssertEqual(proof.registered_operations,1)
        XCTAssertEqual(proof.memory_items,0);XCTAssertEqual(proof.forbidden_writes,0)
        let expected=language=="en" ? "Please explicitly select a formal Trip, local date or item." : "请明确选择正式行程、当地日期或条目。"
        XCTAssertEqual(proof.text,expected)
        tap("run.snapshot.read");text("run.display.status",contains:language=="en" ? "Completed" : "已完成")
        text("run.display.text",contains:expected)
        capture(name+"-actual-unbound-clarification");try audit(name)
    }
    func testUnboundEnglish() async throws { try await unbound("testUnboundEnglish",language:"en") }
    func testUnboundChineseLarge() async throws { try await unbound("testUnboundChineseLarge",language:"zh-Hans",large:true) }
    func testMemoryUpgradeRefused() async throws {
        let f=try await prepare("testMemoryUpgradeRefused");defer { app?.terminate() }
        try launch(f,language:"en");conversation(f)
        tap("assistant.trip.none")
        enter("SYNTHETIC retained draft",language:"en")
        tap("assistant.send")
        text("assistant.trip.refusal",contains:"HTTP 503")
        text("assistant.trip.refusal",contains:"acceptance may still be unknown")
        text("assistant.trip.refusal",contains:"The App did not disable existing memory")
        let send=app.buttons.matching(identifier:"assistant.send").firstMatch
        XCTAssertTrue(send.exists);XCTAssertFalse(send.isEnabled)
        let proof=try JSONDecoder().decode(Proof.self,from:await call("/proof",caseID:f.case_id))
        XCTAssertTrue(proof.upgrade_refused);XCTAssertEqual(proof.memory_items,1)
        XCTAssertEqual(proof.messages,0);XCTAssertEqual(proof.posts,1);XCTAssertEqual(proof.post_statuses,[503])
        XCTAssertEqual(proof.model_calls,0);XCTAssertEqual(proof.registered_operations,0);XCTAssertEqual(proof.forbidden_writes,0)
        capture("memory-upgrade-refused");try audit("memory-upgrade-refused")
    }
}
