import XCTest
import CryptoKit

/// Authorized synthetic beta scenarios. Read-only methods preserve the original
/// records; business methods use only the explicit synthetic acceptance scopes.
/// No message, model, cancellation or account-deletion request is dispatched.
@MainActor final class DevelopmentBetaUITests: XCTestCase {
    private let bundle="space.go2china.beta.acceptance"
    private let original="hk-api-smoke-20261105-05"
    private let answerSHA="4c995378812add4fda098d0fe076e19413f0827cefec9b4aaa14c3a8b3299a8b"
    private let typedFixtureBase64="__BETA_TYPED_CONFIG__"
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
            let element=query.count==1 ? query.element:businessElement(id)
            if query.count==1 {device.revealControl(element,in:app)}
            XCTAssertTrue(element.isEnabled,id);element.tap()
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
    private func enterFresh(_ id:String,_ value:String,done:String?=nil) {
        let element=businessElement(id)
        XCTAssertTrue(element.elementType == .textView || element.elementType == .textField,id)
        XCTAssertTrue(element.isEnabled,id);element.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout:10))
        let doneButtons=done.map {app.buttons.matching(identifier:$0)}
            ?? app.toolbars.buttons.matching(NSPredicate(format:"label IN %@",["Done","完成"]))
        device.revealControl(element,in:app,keyboardDone:doneButtons.element)
        var entered=""
        for character in value {
            element.typeText(String(character));entered.append(character)
            XCTAssertEqual(Array((element.value as? String ?? "").utf8),Array(entered.utf8),id)
        }
        XCTAssertEqual(Array((element.value as? String ?? "").utf8),Array(value.utf8),id)
        XCTAssertEqual(doneButtons.count,1);XCTAssertTrue(doneButtons.element.isHittable && doneButtons.element.isEnabled)
        doneButtons.element.tap();device.handleAppConsent()
        let hidden=XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == false"),object:app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for:[hidden],timeout:5),.completed)
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

    private struct TypedContext:Decodable {let kind:String;let id:String;let expected_version:Int}
    private struct TypedSeed:Decodable {
        let item_id:String;let text:String;let occurred_at:String;let source_id:String
        let source_version:Int;let version:Int;let extent:String;let context:TypedContext?
    }
    private struct TypedFixture:Decodable {
        let owner:String;let environment:[String:String];let travels:[String]
        let travel_versions:[String:Int];let seeds:[TypedSeed]
    }
    private func memoryRoot() {
        tab(["Memory","记忆"])
        if app.staticTexts.matching(identifier:"account.development.status").element.exists {memoryBack()}
    }
    private func memoryBack() {
        let back=app.navigationBars.firstMatch.buttons
        XCTAssertEqual(back.count,1);XCTAssertTrue(back.element.isHittable);back.element.tap()
    }
    private func typedScope(_ context:TypedContext?,language:String) -> String {
        guard let context else {return language=="en" ? "Long-term memory":"长期记忆"}
        return (language=="en" ? "Travel: ":"旅行：")+context.id+" · "+(language=="en" ? "version ":"版本 ")+String(context.expected_version)
    }
    private func typedText(_ id:String) -> String {
        let element=businessElement(id)
        return element.value as? String ?? element.label
    }
    private func typedReadVersion(language:String) throws -> Int {
        let prefix=language=="en" ? "Item version: ":"条目版本："
        let value=typedText("memory2.detail.version");XCTAssertTrue(value.hasPrefix(prefix))
        let version=try XCTUnwrap(Int(value.dropFirst(prefix.count)));XCTAssertGreaterThan(version,0)
        exactText("memory2.detail.version",prefix+String(version));return version
    }
    private func typedAssertDetail(text:String,time:String,scope:String,source:String,version:Int,status:String,language:String) {
        // Version first waits for the fresh response, before reading its fields.
        exactText("memory2.detail.version",(language=="en" ? "Item version: ":"条目版本：")+String(version))
        exactText("memory2.detail.text",text);exactText("memory2.detail.time",time)
        exactText("memory2.detail.subject","self · preference · "+(language=="en" ? "Preferences":"偏好"))
        exactText("memory2.detail.scope",scope);exactText("memory2.detail.source",source)
        exactText("memory2.detail.status",status=="active" ? (language=="en" ? "Active":"已启用"):(language=="en" ? "Disabled":"已停用"))
    }
    private func typedOpenItem(_ id:String,root:Bool) {
        if root {memoryRoot();businessTap("memory2.items.open")}
        businessTap("memory2.items.read")
        businessTap("memory2.item."+id);businessTap("memory2.detail.read")
    }
    private func typedChooseTravel(_ id:String,version:Int,language:String) {
        tab(["Assistant","助手"]);businessTap("assistant.travelContext");businessTap("travel.selection."+id)
        exactText("travel.selection.status",(language=="en" ? "Selected travel: ":"已选旅行：")+id+" · "+(language=="en" ? "version ":"版本 ")+String(version))
        businessTap("assistant.panel.done");memoryRoot()
    }
    private func typedManagement(_ operation:String,text:String,scope:String,version:Int,sourceVersion:Int,status:String,language:String) throws {
        businessTap("memory2.manage.review."+operation)
        exactText("memory2.manage.review.before",text);exactText("memory2.manage.review.scope",scope)
        exactText("memory2.manage.review.versions",(language=="en" ? "Item/source versions: ":"条目/来源版本：")+String(version)+"/"+String(sourceVersion))
        try app.performAccessibilityAudit(for:.all)
        // Exactly one explicit confirmation. UNKNOWN never permits another POST.
        businessTap("memory2.manage.confirm")
        let value=businessElement("memory2.manage.status")
        let prefix=language=="en" ? "Original receipt verified: ":"原回执已核实："
        let condition=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label BEGINSWITH %@ OR value BEGINSWITH %@",prefix,prefix),object:value)
        XCTAssertEqual(XCTWaiter.wait(for:[condition],timeout:30),.completed)
        let raw=value.value as? String ?? value.label
        let label=status=="active" ? (language=="en" ? "Active":"已启用"):(language=="en" ? "Disabled":"已停用")
        let suffix=" · "+String(version+1)+" · "+label+(language=="en" ? ". Read current detail to verify current use.":"。当前是否使用请重新读取详情。")
        XCTAssertTrue(raw.hasPrefix(prefix) && raw.hasSuffix(suffix))
        let action=String(raw.dropFirst(prefix.count).dropLast(suffix.count));XCTAssertNotNil(UUID(uuidString:action))
        print("M4_BETA_TYPED_ACTION",operation,action,"version",version+1,"status",status)
        businessTap("memory2.detail.read")
    }
    private func typedReconcileOriginals(language:String) {
        businessTap("memory.manage.openOriginals");businessTap("memory2.originals.read")
        for id in actionButtons(prefix:"memory2.original.query.").sorted() {
            businessTap(id);exactText("memory2.save.status",typedSavedMessage(language))
        }
        for id in actionButtons(prefix:"memory2.action.query.").sorted() {
            businessTap(id)
            let value=businessElement("memory2.manage.status")
            let action=String(id.dropFirst("memory2.action.query.".count))
            let prefix=(language=="en" ? "Original receipt verified: ":"原回执已核实：")+action+" · "
            let expected=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label BEGINSWITH %@ OR value BEGINSWITH %@",prefix,prefix),object:value)
            XCTAssertEqual(XCTWaiter.wait(for:[expected],timeout:30),.completed)
        }
        memoryBack()
    }
    private func typedSavedMessage(_ language:String) -> String {
        language=="en" ? "Saved. Current use depends on its current status.":"已保存；当前是否使用取决于条目当前状态。"
    }
    private func typedReviewDraft(text:String,time:String,current:Bool,scope:String,language:String) throws {
        businessTap("memory.add");businessTap("memory2.manual.option")
        let label="self · preference · "+(current ? "Selected travel / 所选旅行":"Long term / 长期")
        let menu=app.menuItems.matching(identifier:label)
        let option=menu.element.waitForExistence(timeout:1) ? menu:app.buttons.matching(identifier:label)
        XCTAssertEqual(option.count,1);XCTAssertTrue(option.element.isHittable);option.element.tap()
        enterFresh("memory2.manual.text",text);enterFresh("memory2.manual.time",time)
        businessTap("memory2.manual.review")
        exactText("memory2.review.text",text);exactText("memory2.review.time",time)
        exactText("memory2.review.subject","self · preference · "+(language=="en" ? "Preferences":"偏好"))
        exactText("memory2.review.scope",scope);try app.performAccessibilityAudit(for:.all)
    }
    private func typedAPIOnly(language:String,current:Bool,caseID:String) async throws {
        continueAfterFailure=false;executionTimeAllowance=840;defer {app?.terminate()}
        let fixture=try JSONDecoder().decode(TypedFixture.self,from:XCTUnwrap(Data(base64Encoded:typedFixtureBase64)))
        try await device.stageAccounts(caseID:caseID)
        launch(language:language,injecting:true,profile:fixture.environment);signIn("B");memoryRoot()
        typedReconcileOriginals(language:language)
        let seeds=fixture.seeds.filter {($0.extent=="current")==current}
        XCTAssertEqual(seeds.count,current ? 2:1)
        var createdIDs:[String]=[]
        let first=try XCTUnwrap(seeds.first)
        if let context=first.context {
            typedChooseTravel(context.id,version:try XCTUnwrap(fixture.travel_versions[context.id]),language:language)
        }
        // Diagnose permissions/input/navigation/AX before any seed mutation.
        // The preview creates no durable original and is never confirmed.
        try typedReviewDraft(text:"SYNTHETIC unsubmitted preflight "+UUID().uuidString+" e\u{301} 🌏",
            time:"time unknown / 时间不详",current:current,scope:typedScope(first.context,language:language),language:language)
        memoryBack()
        for seed in seeds {
            if let context=seed.context {
                typedChooseTravel(context.id,version:try XCTUnwrap(fixture.travel_versions[context.id]),language:language)
            }
            typedOpenItem(seed.item_id,root:true)
            let before=try typedReadVersion(language:language);XCTAssertGreaterThanOrEqual(before,seed.version)
            XCTAssertLessThan(before,Int.max-8)
            let source=(language=="en" ? "Source: ":"来源：")+seed.source_id+" · "+String(seed.source_version)
            let scope=typedScope(seed.context,language:language)
            typedAssertDetail(text:seed.text,time:seed.occurred_at,scope:scope,source:source,version:before,status:"active",language:language)
            try app.performAccessibilityAudit(for:.all)
            print("M4_BETA_TYPED_WINDOW_BEGIN",seed.item_id,"version",before)
            try typedManagement("pause",text:seed.text,scope:scope,version:before,sourceVersion:seed.source_version,status:"disabled",language:language)
            typedAssertDetail(text:seed.text,time:seed.occurred_at,scope:scope,source:source,version:before+1,status:"disabled",language:language)
            memoryBack();memoryBack()
            let nonce=UUID().uuidString
            let ownText="SYNTHETIC App API-only "+language+" "+seed.extent+" "+nonce+" e\u{301} 🌏"
            let time="time unknown / 时间不详"
            print("M4_BETA_TYPED_NEW_MARKER",nonce,seed.extent,seed.context?.id ?? "long_term")
            try typedReviewDraft(text:ownText,time:time,current:current,scope:scope,language:language)
            businessTap("memory2.manual.confirm");exactText("memory2.save.status",typedSavedMessage(language))
            memoryBack();businessTap("memory2.items.open");businessTap("memory2.items.read")
            // Discover the App-generated ID by exact original text inside the
            // documented text-ID namespace, then activate only the exact ID.
            let row=app.descendants(matching:.any).matching(NSPredicate(format:"identifier BEGINSWITH %@ AND (label == %@ OR value == %@)","memory2.item.text.",ownText,ownText))
            device.revealControl(row.element,in:app);XCTAssertEqual(row.count,1)
            let ownID=String(row.element.identifier.dropFirst("memory2.item.text.".count));XCTAssertNotNil(UUID(uuidString:ownID))
            createdIDs.append(ownID)
            businessTap("memory2.item."+ownID);businessTap("memory2.detail.read")
            exactText("memory2.detail.version",language=="en" ? "Item version: 1":"条目版本：1")
            let ownSource=typedText("memory2.detail.source")
            XCTAssertTrue(ownSource.hasPrefix(language=="en" ? "Source: ":"来源：") && ownSource.hasSuffix(" · 1"))
            XCTAssertGreaterThan(ownSource.count,(language=="en" ? "Source: ":"来源：").count+" · 1".count)
            typedAssertDetail(text:ownText,time:time,scope:scope,source:ownSource,version:1,status:"active",language:language)
            for (operation,version,status) in [("pause",1,"disabled"),("resume",2,"active"),("pause",3,"disabled")] {
                try typedManagement(operation,text:ownText,scope:scope,version:version,sourceVersion:1,status:status,language:language)
                typedAssertDetail(text:ownText,time:time,scope:scope,source:ownSource,version:version+1,status:status,language:language)
            }
            try app.performAccessibilityAudit(for:.all)
            memoryBack();typedOpenItem(seed.item_id,root:false)
            typedAssertDetail(text:seed.text,time:seed.occurred_at,scope:scope,source:source,version:before+1,status:"disabled",language:language)
            try typedManagement("resume",text:seed.text,scope:scope,version:before+1,sourceVersion:seed.source_version,status:"active",language:language)
            typedAssertDetail(text:seed.text,time:seed.occurred_at,scope:scope,source:source,version:before+2,status:"active",language:language)
            try app.performAccessibilityAudit(for:.all)
            print("M4_BETA_TYPED_WINDOW_RESTORED",seed.item_id,"version",before+2,"retained_disabled_item",ownID)
            memoryBack();memoryBack()
        }
        // Account A deliberately has no B typed policy. This asserts the
        // observed error/no-private-data UI, not a cause inferred from HTTP503.
        app.terminate();try await device.stageAccounts(caseID:caseID)
        launch(language:language,injecting:true,profile:fixture.environment);signIn("A");memoryRoot()
        businessTap("memory2.items.open");businessTap("memory2.items.read")
        exactText("memory2.items.status",language=="en" ? "Memories could not be read. No empty or successful result is assumed.":"无法读取记忆，不能据此视为空列表或读取成功。")
        for id in fixture.seeds.map(\.item_id)+createdIDs {XCTAssertFalse(app.buttons.matching(identifier:"memory2.item."+id).element.exists)}
        XCTAssertFalse(app.descendants(matching:.any).matching(identifier:"memory2.detail.text").element.exists)
        try app.performAccessibilityAudit(for:.all)
    }
    func testBetaBTypedLongTermEnglish() async throws {try await typedAPIOnly(language:"en",current:false,caseID:"beta-typed-long-en")}
    func testBetaBTypedTravelEnglish() async throws {try await typedAPIOnly(language:"en",current:true,caseID:"beta-typed-travel-en")}
    func testBetaBTypedLongTermChinese() async throws {try await typedAPIOnly(language:"zh-Hans",current:false,caseID:"beta-typed-long-zh")}
    func testBetaBTypedTravelChinese() async throws {try await typedAPIOnly(language:"zh-Hans",current:true,caseID:"beta-typed-travel-zh")}
}
