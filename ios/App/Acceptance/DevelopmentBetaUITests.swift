import XCTest
import CryptoKit

/// Actual authorized service, existing synthetic records only. Never sends a
/// message, edits a record, cancels a run or requests account deletion.
@MainActor final class DevelopmentBetaUITests: XCTestCase {
    private let bundle="space.go2china.beta.acceptance"
    private let original="hk-api-smoke-20261105-05"
    private let answerSHA="4c995378812add4fda098d0fe076e19413f0827cefec9b4aaa14c3a8b3299a8b"
    private var app:XCUIApplication!
    private lazy var device=M4DeviceTestSession(test:self,control:"__FIXTURE_URL__")

    private func tap(_ id:String) {
        let control=app.buttons.matching(identifier:id)
        device.revealControl(control.element,in:app)
        XCTAssertEqual(control.count,1);XCTAssertTrue(control.element.isEnabled)
        control.element.tap();device.handleAppConsent()
    }
    private func tab(_ names:[String]) {
        let control=app.tabBars.buttons.matching(NSPredicate(format:"label IN %@",names))
        XCTAssertEqual(control.count,1);XCTAssertTrue(control.element.isHittable)
        control.element.tap();XCTAssertTrue(control.element.isSelected)
    }
    private func launch(language:String,injecting:Bool,profile:[String:String]=[:]) {
        app?.terminate();app=XCUIApplication(bundleIdentifier:bundle)
        app.launchArguments=["-cj.ui.language.v1",language]
        app.launchEnvironment=["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1",
            "G2C_DEV_API_BASE_URL":"https://api-beta.go2china.space","G2C_M4_BETA_API":"1","G2C_DEV_ACCOUNTS":"{}"]
        app.launchEnvironment.merge(profile) {_,value in value}
        let diagnostic=UUID().uuidString
        app.launchEnvironment["G2C_M4_BETA_DIAGNOSTIC_ID"]=diagnostic
        print("M4_BETA_DIAGNOSTIC_ID",diagnostic)
        if injecting {app.launchEnvironment["G2C_M4_ACCOUNTS_FILE"]="G2CM4DeviceAccounts.json"}
        app.launch();XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout:20))
        tab(["Memory","记忆"]);tap("memory.account")
    }
    private func signIn(_ account:String) {
        tap("account.development.signout");tap("account.development.signin."+account)
        device.waitForAppNetworkConsent()
        device.requireAccount("m4-synthetic-beta-"+account.lowercased(),in:app)
    }
    private func originalAnswer() throws {
        tab(["Assistant","助手"]);tap("assistant.serverHistory");tap("history.loadConversations")
        let conversation=app.buttons.matching(identifier:"history.conversation."+original)
        XCTAssertTrue(conversation.element.waitForExistence(timeout:25));tap("history.conversation."+original)
        tap("history.loadMessages")
        let message=app.textViews.matching(identifier:"history.message."+original)
        XCTAssertTrue(message.element.waitForExistence(timeout:25));XCTAssertEqual(message.count,1)
        tap("history.answer.read."+original)
        let text=app.textViews.matching(identifier:"history.answer.text."+original)
        XCTAssertTrue(text.element.waitForExistence(timeout:90));XCTAssertEqual(text.count,1)
        let value=try XCTUnwrap(text.element.value as? String),bytes=Data(value.utf8)
        XCTAssertEqual(bytes.count,224)
        XCTAssertEqual(SHA256.hash(data:bytes).map {String(format:"%02x",$0)}.joined(),answerSHA)
        // Keep every audit category, including contrast/hit-region/text checks.
        try app.performAccessibilityAudit(for:.all)
        let shot=XCTAttachment(screenshot:app.screenshot());shot.name="beta-original-answer";shot.lifetime = .keepAlways;add(shot)
    }
    func testExistingAnswerRestoreAndOwnerIsolation() async throws {
        continueAfterFailure=false;defer {app?.terminate()}
        try await device.stageAccounts(caseID:"beta-readonly-05")
        launch(language:"en",injecting:true);signIn("A");try originalAnswer()
        try await restoreChineseAndCheckOwner()
    }
    private func restoreChineseAndCheckOwner() async throws {
        launch(language:"zh-Hans",injecting:false);tap("account.development.restore")
        device.waitForAppNetworkConsent();device.requireAccount("m4-synthetic-beta-a",in:app)
        try originalAnswer()
        app.terminate();try await device.stageAccounts(caseID:"beta-readonly-05")
        launch(language:"zh-Hans",injecting:true);signIn("B")
        tab(["Assistant","助手"]);tap("assistant.serverHistory");tap("history.loadConversations")
        let empty=app.staticTexts.matching(NSPredicate(format:"label == %@","本次读取未返回记录。"))
        XCTAssertTrue(empty.element.waitForExistence(timeout:25));XCTAssertEqual(empty.count,1)
        XCTAssertFalse(app.buttons["history.conversation."+original].exists)
        XCTAssertFalse(app.textViews["history.message."+original].exists)
        XCTAssertFalse(app.textViews["history.answer.text."+original].exists)
        try app.performAccessibilityAudit(for:.all)
        tap("assistant.panel.done");tab(["Memory","记忆"]);tap("memory.account");tap("account.development.signout")
        XCTAssertFalse(app.staticTexts["account.development.status"].label.contains("m4-synthetic-beta-"))
    }
    func testChineseRecoveryAndOwnerIsolation() async throws {
        continueAfterFailure=false;defer {app?.terminate()}
        try await device.stageAccounts(caseID:"beta-readonly-05")
        launch(language:"en",injecting:true);signIn("A")
        // English answer/AX evidence is already valid; establish fresh material
        // then execute only the missing Chinese restore and owner-isolation path.
        try await restoreChineseAndCheckOwner()
    }
    func testOriginalEnglishDiagnostic() async throws {
        continueAfterFailure=false;defer {app?.terminate()}
        try await device.stageAccounts(caseID:"beta-readonly-05")
        launch(language:"en",injecting:true);signIn("A");try originalAnswer()
    }

    private func businessElement(_ id:String) -> XCUIElement {
        let query=app.descendants(matching:.any).matching(identifier:id)
        let element=query.element
        device.revealControl(element,in:app)
        XCTAssertEqual(query.count,1,id);XCTAssertTrue(element.isHittable,id)
        return element
    }
    private func businessTap(_ id:String) {
        let query=app.buttons.matching(identifier:id)
        let chrome=app.navigationBars.buttons.matching(identifier:id)
        if chrome.count==1 {
            XCTAssertEqual(query.count,1,id);XCTAssertTrue(query.element.isHittable && query.element.isEnabled,id)
            query.element.tap()
        } else {
            let element=businessElement(id);XCTAssertTrue(element.isEnabled,id);element.tap()
        }
        device.handleAppConsent()
    }
    @discardableResult private func exactText(_ id:String,_ expected:String) -> String {
        let element=businessElement(id)
        let predicate=NSPredicate(format:"label == %@ OR value == %@",expected,expected)
        XCTAssertEqual(XCTWaiter.wait(for:[XCTNSPredicateExpectation(predicate:predicate,object:element)],timeout:30),.completed,id)
        let editable=element.elementType == .textView || element.elementType == .textField
        let actual=editable ? (element.value as? String ?? element.label) : element.label
        XCTAssertEqual(Array(actual.utf8),Array(expected.utf8),id)
        return actual
    }
    private func openGeneral() {
        tab(["Memory","记忆"])
        if app.staticTexts.matching(identifier:"account.development.status").element.exists {
            let back=app.navigationBars.buttons;XCTAssertEqual(back.count,1);XCTAssertTrue(back.element.isHittable);back.element.tap()
        }
        businessTap("memory.feedback");XCTAssertFalse(app.switches.matching(identifier:"feedback.associate").element.exists)
    }

    func testGeneralFeedbackOriginalRecoveryOnly() async throws {
        continueAfterFailure=false;executionTimeAllowance=900;defer {app?.terminate()}
        let caseID="beta-general-feedback-recovery"
        let profile=["G2C_DEV_FEEDBACK_PROFILE":"feedback-v1"]
        let pending="feedback.pending.__FEEDBACK_ORIGINAL_ID__"
        let expectedSHA="__FEEDBACK_ORIGINAL_PROBLEM_SHA__"

        try await device.stageAccounts(caseID:caseID)
        launch(language:"en",injecting:true,profile:profile);signIn("A")
        launch(language:"zh-Hans",injecting:false,profile:profile);businessTap("account.development.restore")
        device.waitForAppNetworkConsent();device.requireAccount("m4-synthetic-beta-a",in:app);openGeneral()
        businessTap("feedback.loadPending");exactText("feedback.status","请填写反馈。")
        businessTap(pending)
        let problem=businessElement("feedback.problem")
        XCTAssertTrue(problem.elementType == .textField || problem.elementType == .textView)
        let bytes=Data(try XCTUnwrap(problem.value as? String).utf8)
        XCTAssertEqual(SHA256.hash(data:bytes).map {String(format:"%02x",$0)}.joined(),expectedSHA)
        exactText("feedback.expectation","Explain the saved state clearly.")
        businessTap("feedback.query");exactText("feedback.status","反馈已提交。")
        XCTAssertFalse(app.switches.matching(identifier:"feedback.associate").element.exists)
        XCTAssertFalse(app.descendants(matching:.any).matching(identifier:"feedback.originalref.message").element.exists)
        XCTAssertFalse(app.descendants(matching:.any).matching(identifier:"feedback.originalref.run").element.exists)
        try app.performAccessibilityAudit(for:.all)

        app.terminate();try await device.stageAccounts(caseID:caseID)
        launch(language:"zh-Hans",injecting:true,profile:profile);signIn("B");openGeneral();businessTap("feedback.loadPending")
        exactText("feedback.status","请填写反馈。")
        XCTAssertFalse(app.buttons.matching(identifier:pending).element.exists)
        try app.performAccessibilityAudit(for:.all)
    }
}
