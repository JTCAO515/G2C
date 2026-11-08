import XCTest
import CryptoKit

/// Actual authorized service. Existing-record methods are read-only. The
/// explicit internal composition method requires a dedicated disposable subject.
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
    private func launch(language:String,injecting:Bool,profile:[String:String]=[:],applicationBundle:String?=nil) {
        app?.terminate();app=XCUIApplication(bundleIdentifier:applicationBundle ?? bundle)
        app.launchArguments=["-cj.ui.language.v1",language]
        app.launchEnvironment=["OS_ACTIVITY_MODE":"disable","G2C_DEV_ACCOUNT_MODE":"1",
            "G2C_DEV_API_BASE_URL":"https://api-beta.go2china.space","G2C_M4_BETA_API":"1","G2C_DEV_ACCOUNTS":"{}"]
        app.launchEnvironment.merge(profile) {_,value in value}
        if applicationBundle == nil {
            let diagnostic=UUID().uuidString
            app.launchEnvironment["G2C_M4_BETA_DIAGNOSTIC_ID"]=diagnostic
            print("M4_BETA_DIAGNOSTIC_ID",diagnostic)
        }
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

    private struct CompositionFixture: Decodable {
        let language, account, subject, conversation_id, needs_id, travel_id: String
        let memory_profile, memory_subject, memory_slot: String
    }

    @discardableResult private func readLabel(_ id: String, containing expected: String, timeout: TimeInterval = 45) -> String {
        let query = app.descendants(matching: .any).matching(identifier: id)
        let element = query.element
        XCTAssertTrue(element.waitForExistence(timeout: timeout), id)
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@ OR value CONTAINS %@", expected, expected), object: element)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: timeout), .completed, id)
        XCTAssertEqual(query.count, 1, id)
        if let value = element.value as? String, value.contains(expected) { return value }
        return element.label
    }

    private func fill(_ id: String, with value: String, replace: Bool = false) {
        let query = device.textInputQuery(id, in: app)
        let field = query.element
        device.revealControl(field, in: app)
        XCTAssertEqual(query.count, 1, id)
        XCTAssertTrue(field.isEnabled && field.isHittable, id)
        field.tap()
        if replace {
            field.coordinate(withNormalizedOffset: .init(dx: 0.95, dy: 0.95)).tap()
            M4DeviceTestSession.clearFocusedTextWithKeyboard(field)
        }
        field.typeText(value)
        XCTAssertEqual(Array((field.value as? String ?? "").utf8), Array(value.utf8), id)
    }

    private func dismissKeyboard(_ title: String) {
        let done = app.toolbars.buttons.matching(identifier: title)
        XCTAssertTrue(done.element.waitForExistence(timeout: 8))
        XCTAssertEqual(done.count, 1)
        XCTAssertTrue(done.element.isHittable)
        done.element.tap()
        XCTAssertFalse(app.keyboards.element.exists)
    }

    private func backFrom(_ title: String) {
        let back = app.navigationBars.matching(identifier: title).element.buttons
        XCTAssertEqual(back.count, 1, title)
        XCTAssertTrue(back.element.isHittable, title)
        back.element.tap()
    }

    private func readCompletedRun(_ completed: String) {
        let button = app.buttons.matching(identifier: "run.snapshot.read").element
        let status = app.descendants(matching: .any).matching(identifier: "run.display.status").element
        let deadline = Date().addingTimeInterval(210)
        while Date() < deadline {
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true AND enabled == true"), object: button)
            guard XCTWaiter.wait(for: [ready], timeout: 20) == .completed else { break }
            businessTap("run.snapshot.read")
            let done = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", completed), object: status)
            if XCTWaiter.wait(for: [done], timeout: 15) == .completed { return }
        }
        XCTFail("The original run did not produce a verified completed snapshot")
    }

    func testInternalComposition() async throws {
        continueAfterFailure = false
        executionTimeAllowance = 1800
        defer { app?.terminate() }
        let (data, response) = try await device.data("/m4-composition")
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        let fixture = try JSONDecoder().decode(CompositionFixture.self, from: data)
        XCTAssertTrue(fixture.subject.hasPrefix("m4-synthetic-660-"))
        XCTAssertTrue(["A", "B"].contains(fixture.account))
        XCTAssertTrue(["en", "zh-Hans"].contains(fixture.language))
        let chinese = fixture.language == "zh-Hans"
        func label(_ english: String, _ mandarin: String) -> String { chinese ? mandarin : english }
        let origin = "https://api-beta.go2china.space"
        let travel = try JSONSerialization.data(withJSONObject: ["version": "app-travel.1", "travel_ids": [fixture.travel_id]])
        let profile = [
            "G2C_M4_BETA_COMPOSITION": "internal-v1", "G2C_DEV_CLEANUP_PROFILE": "device-v4",
            "G2C_DEV_OFFLINE_TRIP": "last-sync-v1", "G2C_DEV_TRIP_MANUAL_PROFILE": "manual-v1",
            "G2C_DEV_FEEDBACK_PROFILE": "feedback-v1", "G2C_DEV_NEEDS_PROFILE": "manual-v1",
            "G2C_DEV_NEEDS_ID": fixture.needs_id, "G2C_DEV_TRAVEL_PROFILE": String(decoding: travel, as: UTF8.self),
            "G2C_DEV_TYPED_MEMORY_PROFILE": fixture.memory_profile, "G2C_DEV_TYPED_MEMORY_URL": origin,
            "G2C_DEV_MEMORY_ERASURE_URL": origin,
        ]
        try await device.stageAccounts(caseID: "beta-internal-composition")
        launch(language: fixture.language, injecting: true, profile: profile, applicationBundle: "space.go2china.device-v4.acceptance")
        businessTap("account.development.signin." + fixture.account)
        device.waitForAppNetworkConsent()
        device.requireAccount(fixture.subject, in: app)
        exactText("account.development.status", label("Signed in as ", "已登录：") + fixture.subject)
        try app.performAccessibilityAudit(for: .all)

        print("M4_COMPOSITION_STAGE planning")
        tab(["Assistant", "助手"])
        businessTap("assistant.serverHistory"); businessTap("history.loadConversations")
        XCTAssertFalse(app.buttons["history.conversation." + original].exists)
        businessTap("history.conversation." + fixture.conversation_id); businessTap("assistant.panel.done")
        businessTap("assistant.needs"); businessTap("needs.read")
        readLabel("needs.container.state", containing: label("User-provided details loaded", "已读取"))
        businessTap("assistant.panel.done")
        businessTap("assistant.travelContext"); businessTap("travel.selection." + fixture.travel_id); businessTap("assistant.panel.done")
        let intentQuery = app.switches.matching(identifier: "assistant.intent")
        let intent = intentQuery.element
        device.revealControl(intent, in: app)
        XCTAssertEqual(intentQuery.count, 1)
        XCTAssertEqual(intent.switches.count, 1)
        let toggle = intent.switches.element
        XCTAssertEqual(toggle.value as? String, "0")
        toggle.tap(); XCTAssertEqual(toggle.value as? String, "1")
        fill("assistant.draft", with: label(
            "Plan from my saved needs. Keep the name and address in Chinese, show the local dates and any CNY cost, and mark uncertainty.",
            "请根据已保存需求规划。保留中文地名和地址，标注当地日期、人民币金额与未确认事项。"))
        dismissKeyboard(label("Done", "完成")); businessTap("assistant.send")
        readCompletedRun(label("Completed", "已完成"))
        readLabel("run.draft.status", containing: label("Draft candidate recorded", "已记录草稿候选"))
        let answer = businessElement("run.display.text")
        let answerText = try XCTUnwrap(answer.value as? String)
        XCTAssertFalse(answerText.isEmpty)
        try app.performAccessibilityAudit(for: .all)

        print("M4_COMPOSITION_STAGE accept-and-edit")
        businessTap("planning.discover"); businessTap("planning.accept")
        exactText("planning.receipt.version", label("Committed version 1", "已提交版本 1"))
        let formal = readLabel("planning.formal.version", containing: " · 1")
        let prefix = label("Current formal read: ", "当前正式读回：")
        XCTAssertTrue(formal.hasPrefix(prefix) && formal.hasSuffix(" · 1"))
        let tripID = String(formal.dropFirst(prefix.count).dropLast(" · 1".count))
        XCTAssertFalse(tripID.isEmpty)
        tab(["Trips", "行程"]); businessTap("trip.structured.refresh"); businessTap("trip.structured.item." + tripID)
        businessTap("trip.manual.needs.read"); businessTap("trip.manual.edit.open")
        let titleToggle = app.switches.matching(identifier: "trip.manual.title.selected").element
        device.revealControl(titleToggle, in: app)
        XCTAssertTrue(titleToggle.isEnabled && titleToggle.isHittable)
        titleToggle.tap()
        let revisedTitle = label("Synthetic accepted trip · revised title", "合成正式行程 · 修改标题")
        fill("trip.manual.title.value", with: revisedTitle, replace: true)
        businessTap("trip.manual.keyboard.done"); businessTap("trip.manual.prepare")
        exactText("trip.manual.after.title", revisedTitle)
        businessTap("trip.manual.save")
        XCTAssertTrue(readLabel("trip.manual.receipt", containing: " · 2").hasSuffix(" · 2"))
        businessTap("trip.manual.current")
        readLabel("trip.manual.current.version", containing: label("Current observation: version 2.", "当前观测：版本 2；"))
        businessTap("trip.manual.replaceBasis"); exactText("trip.manual.record.title", revisedTitle)
        let items = app.textViews.matching(NSPredicate(format: "identifier BEGINSWITH %@", "trip.manual.record.item.")).allElementsBoundByIndex
        XCTAssertFalse(items.isEmpty)
        let originalItems = try items.map { ($0.identifier, try XCTUnwrap($0.value as? String)) }
        tab(["Memory", "记忆"])
        if app.navigationBars[label("Account", "账号")].exists { backFrom(label("Account", "账号")) }
        businessTap("memory.language"); businessTap(label("简体中文", "English"))
        tab(["Trips", "行程"]); exactText("trip.manual.record.title", revisedTitle)
        for (id, value) in originalItems { exactText(id, value) }
        tab(["Memory", "记忆"]); businessTap(label("English", "简体中文"))
        backFrom(label("Language", "语言"))
        tab(["Trips", "行程"])
        try app.performAccessibilityAudit(for: .all)

        print("M4_COMPOSITION_STAGE memory")
        tab(["Memory", "记忆"])
        if app.navigationBars[label("Account", "账号")].exists { backFrom(label("Account", "账号")) }
        businessTap("memory.add"); businessTap("memory2.manual.option")
        let option = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", fixture.memory_subject + " · " + fixture.memory_slot + " · Long term / 长期"))
        XCTAssertTrue(option.element.waitForExistence(timeout: 10)); XCTAssertEqual(option.count, 1); option.element.tap()
        let memory = label("Synthetic preference for a quiet entrance", "合成偏好：安静的入口")
        fill("memory2.manual.text", with: memory); fill("memory2.manual.time", with: label("Time unknown", "时间不详"))
        dismissKeyboard(label("Done", "完成")); businessTap("memory2.manual.review"); exactText("memory2.review.text", memory)
        businessTap("memory2.manual.confirm"); readLabel("memory2.save.status", containing: label("Saved", "已保存"))
        backFrom(label("Add memory", "新增记忆"))
        businessTap("memory2.items.open"); businessTap("memory2.items.read")
        let item = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", "memory2.item.", memory))
        XCTAssertTrue(item.element.waitForExistence(timeout: 25)); XCTAssertEqual(item.count, 1); item.element.tap()
        businessTap("memory2.detail.read"); exactText("memory2.detail.text", memory)
        let source = readLabel("memory2.detail.source", containing: " · ")
        let edited = label("Synthetic preference for a quieter entrance", "合成偏好：更安静的入口")
        fill("memory2.edit.text", with: edited); dismissKeyboard(label("Done", "完成"))
        for action in ["edit", "pause", "resume", "stopUse"] {
            businessTap("memory2.manage.review." + action); businessTap("memory2.manage.confirm")
            readLabel("memory2.manage.status", containing: label("Original receipt verified", "原回执已核实"))
            businessTap("memory2.detail.read"); exactText("memory2.detail.text", edited)
            XCTAssertEqual(readLabel("memory2.detail.source", containing: " · "), source)
        }
        readLabel("memory2.detail.status", containing: label("Stopped using", "已停止使用"))
        try app.performAccessibilityAudit(for: .all)
        backFrom(label("Memory", "记忆")); backFrom(label("Saved memories", "已保存记忆"))

        print("M4_COMPOSITION_STAGE feedback")
        businessTap("memory.feedback")
        fill("feedback.problem", with: label("Synthetic app flow feedback", "合成流程反馈"))
        fill("feedback.expectation", with: label("Show the saved result clearly", "请清晰显示保存结果"))
        businessTap("feedback.keyboard.done"); XCTAssertFalse(app.keyboards.element.exists)
        businessTap("feedback.submit"); exactText("feedback.status", label("Feedback submitted.", "反馈已提交。"))
        XCTAssertFalse(businessElement("feedback.receipt.date").label.isEmpty)
        XCTAssertFalse(businessElement("feedback.receipt.time").label.isEmpty)
        try app.performAccessibilityAudit(for: .all)
        backFrom(label("Feedback", "问题反馈"))

        print("M4_COMPOSITION_STAGE account-deletion")
        businessTap("memory.account"); exactText("account.development.status", label("Signed in as ", "已登录：") + fixture.subject)
        businessTap("account.deletion.open")
        readLabel("account.deletion.offlineScope", containing: label("14 days", "14 天"))
        businessTap("account.cleanup.review")
        let consent = app.switches.matching(identifier: "account.cleanup.consent").element
        device.revealControl(consent, in: app)
        XCTAssertEqual(consent.value as? String, "0")
        consent.coordinate(withNormalizedOffset: .init(dx: 0.9, dy: 0.5)).tap()
        XCTAssertEqual(consent.value as? String, "1")
        businessTap("account.cleanup.confirm")
        readLabel("account.cleanup.access", containing: label("Account access has stopped", "账号已停止使用"))
        businessTap("account.cleanup.cleanDevice")
        readLabel("account.cleanup.native", containing: label("original local targets are clear", "原调用指定的本机目标已清理"))
        businessTap("account.cleanup.read")
        readLabel("account.cleanup.progress", containing: label("Confirmed for the listed online domains", "列出的线上范围已核实"))
        businessTap("account.cleanup.finalizeControls")
        readLabel("account.cleanup.controls", containing: label("removed and verified", "已移除并核验"))
        try app.performAccessibilityAudit(for: .all)
    }
}
