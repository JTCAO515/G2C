import XCTest
import CryptoKit

/// Authorized synthetic beta scenarios. Read-only methods preserve the original
/// records; business methods create only their own Needs/Feedback actions.
/// No message, model, cancellation or account-deletion request is dispatched.
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

    // New public business coverage uses the same exact locator, keyboard and
    // consent driver. The existing read-only methods above remain unchanged.
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
        if chrome.count==1 || ["needs.keyboard.done","feedback.keyboard.done"].contains(id) {
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
        let actual=element.elementType == .textView ? (element.value as? String ?? element.label) : element.label
        XCTAssertEqual(Array(actual.utf8),Array(expected.utf8),id)
        return actual
    }
    private func enterFresh(_ id:String,_ value:String,done:String) {
        let element=businessElement(id)
        XCTAssertTrue(element.elementType == .textView || element.elementType == .textField,id)
        XCTAssertTrue(element.isEnabled,id);element.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout:10))
        device.revealControl(element,in:app,keyboardDone:app.buttons.matching(identifier:done).element)
        var entered=""
        for character in value {
            element.typeText(String(character));entered.append(character)
            XCTAssertEqual(Array((element.value as? String ?? "").utf8),Array(entered.utf8),id)
        }
        XCTAssertEqual(Array((element.value as? String ?? "").utf8),Array(value.utf8),id)
        businessTap(done);XCTAssertFalse(app.keyboards.firstMatch.exists)
    }
    private func openNeeds() {tab(["Assistant","助手"]);businessTap("assistant.needs")}
    private func readNeeds(_ language:String,version:Int) {
        businessTap("needs.read")
        exactText("needs.container.state",language=="en" ? "User-provided details loaded.":"已读取用户提供的条件。")
        businessTap("needs.detail.open")
        exactText("needs.detail.version",language=="en" ? "Version at read: \(version)":"读取的版本 \(version)")
        exactText("needs.detail.partySize",language=="en" ? "Party size (separate from companions)\nUser provided: 4":"人数（独立于同伴列表）\n用户提供: 4")
        exactText("needs.detail.source",language=="en" ? "Source: user provided; bookings and times are not externally verified.":"来源：用户提供；预订和时间未由外部服务核实。")
    }
    func testBilingualManualNeedsAndOriginalRecovery() async throws {
        continueAfterFailure=false;executionTimeAllowance=900;defer {app?.terminate()}
        for language in ["en","zh-Hans"] {
            let recoveredLanguage=language=="en" ? "zh-Hans":"en"
            let record="m4-a-needs-"+UUID().uuidString.lowercased()
            let profile=["G2C_DEV_NEEDS_PROFILE":"manual-v1","G2C_DEV_NEEDS_ID":record]
            let statement=language=="en" ? "SYNTHETIC explicit correction: 4 travelers e\u{301} 🌏":"合成明确纠正：本次4人 e\u{301} 🌏"
            try await device.stageAccounts(caseID:"beta-manual-needs")
            launch(language:language,injecting:true,profile:profile);signIn("A");openNeeds()
            // Reopening retires in-memory confirmation. Reconcile prior stored
            // originals before permitting a distinct action; never replay them.
            businessTap("needs.originals.read")
            for id in actionButtons(prefix:"needs.original.query.").sorted() {
                businessTap(id)
                exactText("needs.container.state",language=="en" ? "Original action verified against its historical revision.":"原动作与历史版本已核对。")
            }
            businessTap("needs.beginNew");businessTap("needs.editor.open");businessTap("needs.editor.partySize.section")
            businessTap("needs.editor.partySize.state")
            let label=language=="en" ? "User provided":"用户提供"
            let menu=app.menuItems.matching(identifier:label)
            let option=menu.element.waitForExistence(timeout:1) ? menu:app.buttons.matching(identifier:label)
            XCTAssertEqual(option.count,1);XCTAssertTrue(option.element.isHittable);option.element.tap()
            enterFresh("needs.editor.partySize.value","4",done:"needs.keyboard.done")
            enterFresh("needs.editor.statement",statement,done:"needs.keyboard.done")
            try app.performAccessibilityAudit(for:.all)
            businessTap("needs.save")
            exactText("needs.container.state",language=="en" ? "Original action verified against its historical revision.":"原动作与历史版本已核对。")
            let receipt=businessElement("needs.receipt")
            let prefix=language=="en" ? "Verified original action: ":"已核对原动作："
            let receiptText=receipt.value as? String ?? receipt.label
            XCTAssertTrue(receiptText.hasPrefix(prefix))
            let action=String(receiptText.dropFirst(prefix.count));XCTAssertNotNil(UUID(uuidString:action))
            print("M4_BETA_NEEDS_ORIGINAL",record,action)
            readNeeds(language,version:1);try app.performAccessibilityAudit(for:.all)
            launch(language:recoveredLanguage,injecting:false,profile:profile);businessTap("account.development.restore")
            device.waitForAppNetworkConsent();device.requireAccount("m4-synthetic-beta-a",in:app);openNeeds()
            businessTap("needs.originals.read");businessTap("needs.original.query."+action)
            exactText("needs.container.state",recoveredLanguage=="en" ? "Original action verified against its historical revision.":"原动作与历史版本已核对。")
            businessTap("needs.history.open");exactText("needs.history.statement",statement)
            readNeeds(recoveredLanguage,version:1);try app.performAccessibilityAudit(for:.all)
            app.terminate();try await device.stageAccounts(caseID:"beta-manual-needs")
            launch(language:recoveredLanguage,injecting:true,profile:profile);signIn("B");openNeeds();businessTap("needs.read")
            // B reports ACCESS_UNAVAILABLE/503, with cause UNKNOWN. Assert the
            // actual error presentation, never relabel it as a null/404 read.
            exactText("needs.container.state",recoveredLanguage=="en" ? "Unable to read; details were not changed.":"暂时无法读取；没有更改条件。")
            XCTAssertFalse(app.descendants(matching:.any).matching(identifier:"needs.detail.version").element.exists)
            XCTAssertFalse(app.descendants(matching:.any).matching(identifier:"needs.receipt").element.exists)
            try app.performAccessibilityAudit(for:.all)
        }
    }
    private func openGeneral() {
        tab(["Memory","记忆"])
        if app.staticTexts.matching(identifier:"account.development.status").element.exists {
            let back=app.navigationBars.buttons;XCTAssertEqual(back.count,1);XCTAssertTrue(back.element.isHittable);back.element.tap()
        }
        businessTap("memory.feedback");XCTAssertFalse(app.switches.matching(identifier:"feedback.associate").element.exists)
    }
    private func actionButtons(prefix:String) -> Set<String> {
        Set(app.buttons.matching(NSPredicate(format:"identifier BEGINSWITH %@",prefix)).allElementsBoundByIndex.map(\.identifier))
    }
    func testBilingualGeneralFeedbackAndOriginalRecovery() async throws {
        continueAfterFailure=false;executionTimeAllowance=900;defer {app?.terminate()}
        let profile=["G2C_DEV_FEEDBACK_PROFILE":"feedback-v1"]
        for language in ["en","zh-Hans"] {
            let recoveredLanguage=language=="en" ? "zh-Hans":"en"
            let nonce=UUID().uuidString
            let problem=(language=="en" ? "SYNTHETIC feedback e\u{301} 🌏 ":"合成反馈 e\u{301} 🌏 ")+nonce
            let expectation=language=="en" ? "Explain the saved state clearly.":"请明确说明保存状态。"
            try await device.stageAccounts(caseID:"beta-general-feedback")
            launch(language:language,injecting:true,profile:profile);signIn("A");openGeneral()
            businessTap("feedback.loadPending");exactText("feedback.status",language=="en" ? "Ready to describe your feedback.":"请填写反馈。")
            let before=actionButtons(prefix:"feedback.pending.")
            for id in before.sorted() {
                businessTap(id);businessTap("feedback.query")
                exactText("feedback.status",language=="en" ? "Feedback submitted.":"反馈已提交。")
            }
            if !before.isEmpty {businessTap("feedback.another")}
            enterFresh("feedback.problem",problem,done:"feedback.keyboard.done")
            enterFresh("feedback.expectation",expectation,done:"feedback.keyboard.done")
            try app.performAccessibilityAudit(for:.all);businessTap("feedback.submit")
            exactText("feedback.status",language=="en" ? "Feedback submitted.":"反馈已提交。")
            XCTAssertFalse(businessElement("feedback.problem").isEnabled)
            try app.performAccessibilityAudit(for:.all)
            businessTap("feedback.loadPending")
            exactText("feedback.status",language=="en" ? "Submission is not confirmed. Keep the original feedback and check its status; do not resubmit.":"提交结果尚未确认。请保留原反馈并查询状态，不要重新提交。")
            let added=actionButtons(prefix:"feedback.pending.").subtracting(before);XCTAssertEqual(added.count,1)
            let pending=try XCTUnwrap(added.first)
            print("M4_BETA_FEEDBACK_ORIGINAL",String(pending.dropFirst("feedback.pending.".count)),SHA256.hash(data:Data(problem.utf8)).map{String(format:"%02x",$0)}.joined())
            launch(language:recoveredLanguage,injecting:false,profile:profile);businessTap("account.development.restore")
            device.waitForAppNetworkConsent();device.requireAccount("m4-synthetic-beta-a",in:app);openGeneral()
            businessTap("feedback.loadPending");exactText("feedback.status",recoveredLanguage=="en" ? "Ready to describe your feedback.":"请填写反馈。")
            businessTap(pending);exactText("feedback.problem",problem);exactText("feedback.expectation",expectation)
            businessTap("feedback.query");exactText("feedback.status",recoveredLanguage=="en" ? "Feedback submitted.":"反馈已提交。")
            XCTAssertFalse(app.switches.matching(identifier:"feedback.associate").element.exists)
            XCTAssertFalse(app.descendants(matching:.any).matching(identifier:"feedback.originalref.message").element.exists)
            XCTAssertFalse(app.descendants(matching:.any).matching(identifier:"feedback.originalref.run").element.exists)
            try app.performAccessibilityAudit(for:.all)
            app.terminate();try await device.stageAccounts(caseID:"beta-general-feedback")
            launch(language:recoveredLanguage,injecting:true,profile:profile);signIn("B");openGeneral();businessTap("feedback.loadPending")
            exactText("feedback.status",recoveredLanguage=="en" ? "Ready to describe your feedback.":"请填写反馈。")
            XCTAssertFalse(app.buttons.matching(identifier:pending).element.exists)
            try app.performAccessibilityAudit(for:.all)
        }
    }
}
