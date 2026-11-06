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
    private func launch(language:String,injecting:Bool) {
        app?.terminate();app=XCUIApplication(bundleIdentifier:bundle)
        app.launchArguments=["-cj.ui.language.v1",language]
        app.launchEnvironment=["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1",
            "G2C_DEV_API_BASE_URL":"https://api-beta.go2china.space","G2C_M4_BETA_API":"1","G2C_DEV_ACCOUNTS":"{}"]
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
        XCTAssertTrue(text.element.waitForExistence(timeout:25));XCTAssertEqual(text.count,1)
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
    func testOriginalEnglishDiagnostic() async throws {
        continueAfterFailure=false;defer {app?.terminate()}
        try await device.stageAccounts(caseID:"beta-readonly-05")
        launch(language:"en",injecting:true);signIn("A");try originalAnswer()
    }
}
