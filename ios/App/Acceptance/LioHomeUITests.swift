import XCTest

@MainActor final class LioHomeUITests: XCTestCase {
    func testEnglish() throws { try exercise("en", question: "How do I take the metro in Shanghai?") }
    func testChinese() throws { try exercise("zh-Hans", question: "在上海怎么坐地铁？") }

    func testInvitationEnglish() throws { try exerciseInvitation("en") }
    func testInvitationChinese() throws { try exerciseInvitation("zh-Hans") }

    func testInterruptionCoversPrivateRootAndPresentedSheet() throws {
        continueAfterFailure = false
        for appearance in ["light", "dark"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-scene-privacy-acceptance", "-lio.ui.appearance.v1", appearance]
            app.launch()
            func verify(_ scope: String, expectedDraft: String) throws {
                let text = app.staticTexts["privacy.\(scope).text"]
                let field = app.textFields["privacy.\(scope).draft"]
                let action = app.buttons["privacy.\(scope).action"]
                XCTAssertTrue(text.waitForExistence(timeout: 10))
                XCTAssertEqual(field.value as? String, expectedDraft)
                let hit = action.frame
                app.buttons["privacy.\(scope).interrupt"].tap()
                XCTAssertFalse(text.exists)
                XCTAssertFalse(field.exists)
                XCTAssertFalse(action.exists)
                XCTAssertFalse(app.navigationBars["Synthetic private \(scope) title"].exists)
                XCTAssertFalse(app.staticTexts["privacy.root.text"].exists)
                XCTAssertFalse(app.textFields["privacy.root.draft"].exists)
                XCTAssertFalse(app.buttons["privacy.root.action"].exists)
                app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: hit.midX, dy: hit.midY)).tap()
                try app.performAccessibilityAudit(for: .all)
                let image = XCTAttachment(screenshot: app.screenshot())
                image.name = "scene-private-\(scope)-\(appearance)"
                image.lifetime = .keepAlways
                add(image)
                app.buttons["lio.privacy.test.resume"].tap()
                XCTAssertTrue(text.waitForExistence(timeout: 8))
                XCTAssertEqual(app.staticTexts["privacy.\(scope).actions"].label, "0")
                XCTAssertEqual(field.value as? String, expectedDraft)
            }
            try verify("root", expectedDraft: "Synthetic root draft")
            app.buttons["privacy.open-sheet"].tap()
            try verify("sheet", expectedDraft: "Synthetic sheet draft")
            app.buttons["privacy.close-sheet"].tap()
            XCTAssertTrue(app.staticTexts["privacy.root.text"].waitForExistence(timeout: 8))
            app.terminate()
        }
    }

    func testSessionRecoveryKeepsExplicitActionsInBothLanguagesAndAppearances() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let chinese = language == "zh-Hans"
                app.launchArguments = ["--lio-preview", "--lio-session-recovery-acceptance",
                                       "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance]
                app.launch()
                let recovery = app.descendants(matching: .any).matching(identifier: "lio.session.recovery").firstMatch
                XCTAssertTrue(recovery.waitForExistence(timeout: 12))
                XCTAssertTrue(app.staticTexts[chinese ? "正在恢复对话…" : "Restoring your chat…"].exists)
                XCTAssertFalse(app.buttons["lio.session.retry"].exists)
                XCTAssertFalse(app.secureTextFields["demo.invite.code"].exists)
                XCTAssertFalse(app.staticTexts["lio.question"].exists)
                XCTAssertFalse(app.staticTexts["lio.answer"].exists)
                try app.performAccessibilityAudit(for: .all)
                let loading = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                loading.name = "Lio-session-loading-" + language + "-" + appearance
                loading.lifetime = .keepAlways
                add(loading)

                app.buttons["synthetic.recovery.offline"].tap()
                let retry = app.buttons["lio.session.retry"]
                XCTAssertTrue(retry.waitForExistence(timeout: 5))
                XCTAssertEqual(retry.label, chinese ? "重试" : "Try again")
                XCTAssertEqual(app.staticTexts["lio.session.notice"].label,
                               chinese ? "暂时连接不上，登录信息仍已保留。"
                                   : "Couldn’t connect. Your sign-in is still saved.")
                try app.performAccessibilityAudit(for: .all)
                let offline = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                offline.name = "Lio-session-offline-" + language + "-" + appearance
                offline.lifetime = .keepAlways
                add(offline)
                retry.tap()
                XCTAssertEqual(app.staticTexts["synthetic.recovery.retry-count"].label, "1")
                XCTAssertFalse(retry.exists)
                let signout = app.buttons["lio.session.signout"]
                XCTAssertEqual(signout.label, chinese ? "退出登录" : "Sign out")
                signout.tap()
                XCTAssertTrue(app.staticTexts["synthetic.recovery.signedout"].waitForExistence(timeout: 5))
                app.terminate()
            }
        }
    }

    func testAppearanceBelowLanguagePersistsInBothLanguages() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            let dark = chinese ? "深色" : "Dark"
            let light = chinese ? "浅色" : "Light"
            let system = chinese ? "跟随系统" : "System"
            let done = chinese ? "完成" : "Done"
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
            app.launch()
            XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
            app.buttons["lio.menu"].tap()
            let appearance = app.buttons["lio.appearance"]
            let languagePicker = app.buttons["lio.language"]
            XCTAssertTrue(appearance.waitForExistence(timeout: 8))
            XCTAssertGreaterThan(appearance.frame.minY, languagePicker.frame.minY)
            appearance.tap()
            app.buttons[dark].tap()
            XCTAssertTrue(appearance.label.contains(dark), appearance.debugDescription)
            app.buttons[done].tap()
            let darkCapture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            darkCapture.name = "Lio-dark-" + language
            darkCapture.lifetime = .keepAlways
            add(darkCapture)

            app.terminate()
            app.launch()
            XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
            app.buttons["lio.menu"].tap()
            XCTAssertTrue(appearance.label.contains(dark), appearance.debugDescription)
            let menuCapture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            menuCapture.name = "Lio-appearance-menu-" + language
            menuCapture.lifetime = .keepAlways
            add(menuCapture)
            appearance.tap()
            app.buttons[light].tap()
            XCTAssertTrue(appearance.label.contains(light), appearance.debugDescription)
            app.buttons[done].tap()
            let lightCapture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            lightCapture.name = "Lio-light-" + language
            lightCapture.lifetime = .keepAlways
            add(lightCapture)
            app.buttons["lio.menu"].tap()
            appearance.tap()
            app.buttons[system].tap()
            XCTAssertTrue(appearance.label.contains(system), appearance.debugDescription)
            app.terminate()
        }
    }

    func testOpeningGreetingReturnsAfterBackgroundWithoutResettingTheChat() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
            app.launch()
            let greeting = app.staticTexts["lio.opening"]
            XCTAssertTrue(greeting.waitForExistence(timeout: 12))
            enterSampleQuestion(in: app, index: 0)
            app.buttons["lio.send"].tap()
            let question = app.staticTexts["lio.question"], answer = app.staticTexts["lio.answer"]
            XCTAssertTrue(answer.waitForExistence(timeout: 8))
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            composer.tap(); composer.typeText("Unsent follow-up")
            let sendReady = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: app.buttons["lio.send"])
            XCTAssertEqual(XCTWaiter.wait(for: [sendReady], timeout: 8), .completed)
            let sentText = question.label, replyText = answer.label
            XCUIDevice.shared.press(.home)
            XCTAssertTrue(app.wait(for: .runningBackground, timeout: 5) || app.state == .runningBackgroundSuspended)
            app.activate()
            XCTAssertTrue(question.waitForExistence(timeout: 8))
            XCTAssertEqual(composer.value as? String, "Unsent follow-up")
            app.scrollViews.firstMatch.swipeDown()
            app.scrollViews.firstMatch.swipeDown()
            XCTAssertTrue(greeting.exists)
            XCTAssertEqual(question.label, sentText)
            XCTAssertEqual(answer.label, replyText)
            XCTAssertLessThan(greeting.frame.minY, question.frame.minY)
            XCTAssertEqual(app.staticTexts.matching(identifier: "lio.opening").count, 1)
            XCTAssertEqual(app.staticTexts.matching(identifier: "lio.question").count, 1)
            app.terminate()
        }
    }

    func testNewChatAndHistoryKeepMessagesAndDraftsSeparate() {
        exerciseChatHistory("en")
    }

    func testChineseNewChatKeepsHistoryAndDraftsSeparate() {
        exerciseChatHistory("zh-Hans")
    }

    func testRecreatedClientReturnsToEnglishConversationAndDraft() { exerciseRecreatedChat("en") }
    func testRecreatedClientReturnsToChineseConversationAndDraft() { exerciseRecreatedChat("zh-Hans") }

    private func exerciseRecreatedChat(_ language: String) {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "--lio-chat-recovery-acceptance", "-cj.ui.language.v1", language]
        app.launchArguments += ["--lio-chat-before-stage-acceptance"]
        app.launch()
        defer { app.terminate() }
        let menu = app.buttons["lio.menu"]
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(composer.waitForExistence(timeout: 12))
        XCTAssertEqual(composer.value as? String, language == "en" ? "A question before staging" : "还没发出的合成问题")
        XCTAssertTrue(app.buttons["lio.send"].isEnabled)
        menu.tap()
        XCTAssertTrue(app.buttons["lio.chat.new"].waitForExistence(timeout: 8))
        app.terminate()
        app.launchArguments.removeAll { $0 == "--lio-chat-before-stage-acceptance" }
        app.launch()
        XCTAssertTrue(menu.waitForExistence(timeout: 12))
        menu.tap(); app.buttons["lio.chat.new"].tap()
        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        enterSampleQuestion(in: app, index: 0); app.buttons["lio.send"].tap()
        XCTAssertTrue(app.staticTexts["A separate reply."].waitForExistence(timeout: 12))
        composer.tap(); composer.typeText("My unsent follow-up")
        menu.tap(); app.buttons["synthetic.chat.recreate"].tap()
        XCTAssertTrue(app.staticTexts["A separate reply."].waitForExistence(timeout: 12), app.debugDescription)
        XCTAssertFalse(app.staticTexts["An earlier reply."].exists)
        XCTAssertEqual(composer.value as? String, "My unsent follow-up")
        XCTAssertFalse(app.otherElements["lio.chat.recovery"].exists)
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
    }

    func testNewChatCanAcceptAnotherMessageAfterAnInputRefusal() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "--lio-chat-first-refusal-acceptance",
                               "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let menu = app.buttons["lio.menu"]
        XCTAssertTrue(menu.waitForExistence(timeout: 12))
        menu.tap()
        app.buttons["lio.chat.new"].tap()
        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        enterSampleQuestion(in: app, index: 0)
        let send = app.buttons["lio.send"]
        send.tap()
        let failure = app.staticTexts["lio.failure"]
        XCTAssertTrue(failure.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertEqual(failure.label, "这条消息没发出去，请换个说法再试。")
        XCTAssertFalse(app.buttons["lio.resend"].exists)
        XCTAssertFalse(app.staticTexts["A separate reply."].exists)

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap()
        composer.typeText("A fresh question")
        send.tap()
        XCTAssertTrue(app.staticTexts["A separate reply."].waitForExistence(timeout: 12), app.debugDescription)
    }

    private func exerciseChatHistory(_ language: String) {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        let chinese = language == "zh-Hans"
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let menu = app.buttons["lio.menu"]
        let oldReply = app.staticTexts["An earlier reply."]
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        menu.tap()
        let newChat = app.buttons["lio.chat.new"]
        XCTAssertEqual(newChat.label, chinese ? "新对话" : "New chat")
        newChat.tap()
        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["lio.opening"].exists)
        XCTAssertFalse(oldReply.exists)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        enterSampleQuestion(in: app, index: 0)
        let firstQuestion = chinese ? "在上海怎么坐地铁？" : "How do I take the metro in Shanghai?"
        XCTAssertEqual(composer.value as? String, firstQuestion)
        app.buttons["lio.send"].tap()
        let newReply = app.staticTexts["A separate reply."]
        XCTAssertTrue(newReply.waitForExistence(timeout: 12), app.debugDescription)
        XCTAssertFalse(oldReply.exists)
        composer.tap()
        let draft = "A follow up draft"
        composer.typeText(draft)

        func openHistory(_ title: String) {
            menu.tap()
            let history = app.buttons["lio.chat.history"]
            XCTAssertEqual(history.label, chinese ? "历史对话" : "Chat history")
            history.tap()
            let row = app.buttons.matching(identifier: "lio.chat.history.row")
                .matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 8))
            row.tap()
        }
        openHistory(chinese ? "最早的对话" : "First conversation")
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        XCTAssertFalse(newReply.exists)
        XCTAssertNotEqual(composer.value as? String, draft)
        openHistory(firstQuestion)
        XCTAssertTrue(newReply.waitForExistence(timeout: 8))
        XCTAssertFalse(oldReply.exists)
        XCTAssertEqual(composer.value as? String, draft)
    }

    private func exerciseInvitation(_ language: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-onboarding-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let field = app.secureTextFields["demo.invite.code"]
        let proceed = app.buttons["demo.invite.continue"]
        let consent = app.descendants(matching: .any).matching(identifier: "demo.invite.consent").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 12))
        XCTAssertFalse(proceed.isEnabled)
        app.buttons["demo.invite.restore"].tap()
        XCTAssertTrue(consent.waitForExistence(timeout: 8))
        app.buttons["lio.invite.back"].tap()
        XCTAssertTrue(field.waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["lio.menu"].exists)

        field.tap()
        field.typeText("LIO-DEMO")
        proceed.tap()
        XCTAssertTrue(consent.waitForExistence(timeout: 8))
        try app.performAccessibilityAudit(for: .all)
        app.buttons["lio.invite.back"].tap()
        XCTAssertTrue(proceed.waitForExistence(timeout: 8))
        XCTAssertTrue(proceed.isEnabled)
        XCTAssertFalse(app.buttons["lio.menu"].exists)
        proceed.tap()
        app.buttons["demo.invite.signin"].tap()
        XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.buttons["lio.example.0"].exists)
    }

    func testJourneyEnglish() throws { try exerciseJourney("en") }
    func testJourneyChinese() throws { try exerciseJourney("zh-Hans") }

    private func exerciseJourney(_ language: String) throws {
        continueAfterFailure = false
        let chinese = language == "zh-Hans"
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        let send = app.buttons["lio.send"]
        let chat = app.tabBars.buttons[chinese ? "聊天" : "Chat"]
        let trips = app.tabBars.buttons[chinese ? "行程" : "Trips"]
        func reply(_ text: String) {
            XCTAssertTrue(app.staticTexts[text].waitForExistence(timeout: 10), app.debugDescription)
        }
        func ask(_ text: String) {
            composer.tap()
            composer.typeText(text)
            XCTAssertTrue(send.isEnabled)
            send.tap()
        }
        func reveal(_ control: XCUIElement) {
            for _ in 0..<4 {
                if control.isHittable { return }
                app.swipeUp()
            }
            XCTAssertTrue(control.isHittable, app.debugDescription)
        }

        let metro = app.buttons["lio.example.0"]
        XCTAssertTrue(metro.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        send.tap()
        XCTAssertTrue(app.staticTexts[chinese ? "Lio 正在回复…" : "Lio is replying…"]
            .waitForExistence(timeout: 3))
        reply(chinese ? "跟着地铁线路指示牌走。" : "Follow the signs for your metro line.")
        XCTAssertFalse(app.buttons["lio.source"].exists)
        XCTAssertFalse(app.staticTexts[chinese ? "正在查旅行信息…" : "Checking travel information…"].exists)

        ask(chinese ? "帮我规划北京两天" : "Plan two days in Beijing")
        reply(chinese ? "你想慢慢逛吗？" : "Would you like a slower pace?")
        XCTAssertFalse(app.buttons["lio.trip.show"].exists)
        ask(chinese ? "慢一点" : "Take it slow")
        reply(chinese ? "北京行程已保存。" : "I saved your Beijing trip.")
        let show = app.buttons["lio.trip.show"]
        reveal(show)
        show.tap()
        let hotel = chinese ? "酒店入住" : "Hotel check-in"
        let park = chinese ? "公园散步" : "Park walk"
        let museum = chinese ? "美术馆" : "Art museum"
        reply(hotel)
        reply(park)
        chat.tap()

        ask(chinese ? "把第二天下午换成美术馆" : "Change the second day to the art museum")
        reply(chinese ? "第二天下午已经改好了。" : "I changed the second afternoon.")
        let undo = app.buttons["lio.chat.trip.undo"]
        XCTAssertTrue(undo.waitForExistence(timeout: 10), app.debugDescription)
        trips.tap()
        reply(hotel)
        reply(museum)
        XCTAssertFalse(app.staticTexts[park].exists)
        chat.tap()
        reveal(undo)
        undo.tap()
        trips.tap()
        reply(park)
        reply(hotel)
        XCTAssertFalse(app.staticTexts[museum].exists)
        let previous = app.buttons["lio.trip.history"]
        XCTAssertTrue(previous.waitForExistence(timeout: 6))
        previous.tap()
        XCTAssertTrue(app.buttons["lio.trip.undo"].waitForExistence(timeout: 6))
        chat.tap()

        ask(chinese ? "我喜欢安静的酒店" : "I prefer quiet hotels")
        let remember = app.buttons["lio.memory.remember"]
        XCTAssertTrue(remember.waitForExistence(timeout: 10))
        XCTAssertEqual(app.buttons.matching(identifier: "lio.memory.remember").count, 1)
        let remembered = app.staticTexts[chinese ? "已记住" : "Remembered"]
        XCTAssertFalse(remembered.exists)
        reveal(remember)
        reply(chinese ? "记住：你喜欢安静的酒店？" : "Remember: You like quiet hotels?")
        remember.tap()
        XCTAssertTrue(remembered.waitForExistence(timeout: 10))
        XCTAssertFalse(remember.exists)
        ask(chinese ? "我适合住哪种酒店" : "What kind of hotel suits me?")
        reply(chinese ? "你喜欢安静的酒店。" : "You like quiet hotels.")

        let memory = app.tabBars.buttons[chinese ? "记忆" : "Memory"]
        memory.tap()
        let preference = chinese ? "你喜欢安静的酒店" : "You like quiet hotels"
        let editedPreference = chinese ? "你喜欢安静且靠近地铁的酒店" : "You like quiet hotels near the metro"
        let otherPreference = chinese ? "你偏好靠过道的座位" : "You prefer an aisle seat"
        reply(otherPreference)
        let saved = app.buttons[preference]
        XCTAssertTrue(saved.waitForExistence(timeout: 8), app.debugDescription)
        saved.tap()
        let edit = app.buttons["lio.memory.edit"]
        XCTAssertTrue(edit.waitForExistence(timeout: 8), app.debugDescription)
        edit.tap()
        let editor = app.descendants(matching: .any).matching(identifier: "lio.memory.editor").firstMatch
        XCTAssertTrue(editor.waitForExistence(timeout: 8))
        editor.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.2)).tap()
        editor.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: preference.count) + editedPreference)
        XCTAssertEqual(editor.value as? String, editedPreference)
        let save = app.buttons["lio.memory.save"]
        reveal(save)
        save.tap()
        reply(editedPreference)
        reply(chinese ? "已保存。" : "Saved.")

        let delete = app.buttons["lio.memory.delete"]
        let confirm = app.buttons["lio.memory.delete.confirm"]
        let deletionTitle = chinese ? "删除记忆" : "Delete memory"
        let done = app.navigationBars[deletionTitle].buttons[chinese ? "完成" : "Done"]
        reveal(delete)
        delete.tap()
        XCTAssertTrue(confirm.waitForExistence(timeout: 8), app.debugDescription)
        let range = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@",
            chinese ? "聊天和已保存行程会保留" : "Your chats and saved trips stay")).firstMatch
        XCTAssertTrue(range.exists)
        done.tap()
        reply(editedPreference)
        reveal(delete)
        delete.tap()
        XCTAssertTrue(confirm.waitForExistence(timeout: 8))
        reveal(confirm)
        confirm.tap()
        XCTAssertTrue(app.staticTexts[chinese ? "Lio 已停止使用这条记忆。" : "Lio has stopped using this memory."]
            .waitForExistence(timeout: 25), app.debugDescription)
        reply(chinese ? "线上清理已完成。" : "Online cleanup is complete.")
        reply(chinese ? "本机已清理这条记忆的保存和编辑记录。"
                      : "This device’s records of saving and editing this memory were cleared.")
        done.tap()
        reply(otherPreference)
        XCTAssertFalse(app.buttons[editedPreference].exists)
        chat.tap()
        ask(chinese ? "再说说我适合住哪种酒店" : "Remind me what kind of hotel suits me")
        reply(chinese ? "你喜欢什么样的酒店？" : "Tell me what kind of hotel you like.")
    }

    func testTripEnglish() throws {
        try exerciseTrip("en", clarification: "For three days in Beijing", trips: "Trips", day: "Day 1", fixed: "Hotel check-in")
    }

    func testTripChinese() throws {
        try exerciseTrip("zh-Hans", clarification: "北京三天", trips: "行程", day: "第 1 天", fixed: "酒店入住")
    }

    func testSavedTripMapLoadsOnlyWhenOpenedAndKeepsTheScheduleOnFailure() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", "en"]
        app.launchEnvironment = [
            "G2C_LIO_PREVIEW_TRIP": "__LIO_RECORDED_TRIP_FIXTURE__",
            "G2C_ACCEPTANCE_MAP_LOADING": "synthetic-delegate-failure"
        ]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.tabBars.buttons["Trips"].waitForExistence(timeout: 12))
        app.tabBars.buttons["Trips"].tap()
        let trip = app.buttons["Draft"]
        XCTAssertTrue(trip.waitForExistence(timeout: 8), app.debugDescription)
        trip.tap()
        let schedule = app.staticTexts["Date to be decided"]
        XCTAssertTrue(schedule.waitForExistence(timeout: 8))
        let map = app.buttons["lio.trip.recorded-map"]
        if !map.isHittable { app.swipeUp() }
        XCTAssertTrue(map.isHittable, app.debugDescription)
        XCTAssertFalse(app.staticTexts["Map unavailable"].exists)
        map.tap()
        XCTAssertTrue(app.staticTexts["Map unavailable"].waitForExistence(timeout: 8))
        XCTAssertTrue(schedule.exists)
    }

    func testHistoricalChatCardOpensTheCurrentSavedTrip() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", "--lio-stale-trip-acceptance",
                               "-cj.ui.language.v1", "en"]
        app.launchEnvironment = ["G2C_LIO_PREVIEW_TRIP": "__LIO_RECORDED_TRIP_FIXTURE__"]
        app.launch()
        defer { app.terminate() }

        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        let viewTrip = app.buttons["lio.trip.show"]
        XCTAssertTrue(viewTrip.waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["Earlier plan"].exists)
        viewTrip.tap()
        XCTAssertTrue(app.navigationBars["Draft"].waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Date to be decided"].exists)
        XCTAssertFalse(app.staticTexts["Earlier plan"].exists)
        XCTAssertFalse(app.staticTexts["Earlier stop"].exists)

        app.tabBars.buttons["Chat"].tap()
        XCTAssertTrue(viewTrip.waitForExistence(timeout: 8))
        viewTrip.tap()
        XCTAssertTrue(app.staticTexts["Trip unavailable"].waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertFalse(app.staticTexts["Date to be decided"].exists)
        XCTAssertFalse(app.staticTexts["Earlier stop"].exists)
    }

    private func exerciseTrip(_ language: String, clarification: String, trips: String, day: String, fixed: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.1"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 1)
        app.buttons["lio.send"].tap()
        let reply = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", clarification)).firstMatch
        XCTAssertTrue(reply.waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["lio.trip.show"].exists)

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap()
        composer.typeText("slow")
        app.buttons["lio.send"].tap()
        let show = app.buttons["lio.trip.show"]
        XCTAssertTrue(show.waitForExistence(timeout: 12))
        XCTAssertFalse(app.staticTexts[fixed].exists)

        let disclosure = app.descendants(matching: .any).matching(identifier: "lio.trip.day.1").firstMatch
        XCTAssertTrue(disclosure.waitForExistence(timeout: 6), app.debugDescription)
        disclosure.tap()
        XCTAssertTrue(app.staticTexts[fixed].waitForExistence(timeout: 6))
        disclosure.tap()
        show.tap()

        XCTAssertTrue(app.navigationBars[trips].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts[fixed].exists)
        app.buttons["lio.trip.map.1"].tap()
        XCTAssertTrue(app.navigationBars[day].waitForExistence(timeout: 8))
    }

    func testResendUsesTheSameQuestionAndQuotaStopsRetry() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", "--lio-resend-acceptance",
                               "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()

        let failure = app.staticTexts["lio.failure"]
        let resend = app.buttons["lio.resend"]
        let questions = app.staticTexts.matching(identifier: "lio.question")
        XCTAssertTrue(resend.waitForExistence(timeout: 8))
        XCTAssertTrue(resend.isHittable)
        XCTAssertEqual(failure.label, "消息没发出去。检查网络后，点感叹号重发。")
        XCTAssertEqual(questions.count, 1)
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")

        resend.tap()
        let quota = app.staticTexts.containing(NSPredicate(format: "label == %@", "今天的问题额度已用完，明天再来聊吧。"))
            .firstMatch
        XCTAssertTrue(quota.waitForExistence(timeout: 8))
        XCTAssertEqual(questions.count, 1)
        XCTAssertEqual(questions.firstMatch.label, "在上海怎么坐地铁？")
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "2")
        XCTAssertFalse(resend.exists)
        XCTAssertFalse(app.buttons["lio.askAgain"].exists)
    }

    func testAcceptedFailureDescribesOnlyTheCurrentRequest() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for (scenario, english, chinese) in [
            ("--lio-accepted-failure-acceptance", "I couldn’t complete this request.", "这次没能完成你的请求。"),
            ("--lio-accepted-limit-acceptance", "Lio couldn’t finish this request within the current limit.", "这次没能在限额内答完。")
        ] {
            for language in ["en", "zh-Hans"] {
                app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", scenario,
                                       "-cj.ui.language.v1", language]
                app.launch()
                defer { app.terminate() }

                let example = app.buttons["lio.example.1"]
                XCTAssertTrue(example.waitForExistence(timeout: 12))
                enterSampleQuestion(in: app, index: 1)
                app.buttons["lio.send"].tap()
                let failure = app.staticTexts["lio.failure"]
                XCTAssertTrue(failure.waitForExistence(timeout: 8))
                XCTAssertEqual(failure.label, language == "en" ? english : chinese)
                XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")
                XCTAssertFalse(app.staticTexts["lio.answer"].exists)
                XCTAssertFalse(app.buttons["lio.source"].exists)
                XCTAssertFalse(app.staticTexts["Amap Weather"].exists)
                XCTAssertFalse(app.buttons["lio.resend"].exists)
                XCTAssertFalse(app.buttons["lio.askAgain"].exists)
                let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                capture.name = "Lio-final-failure-" + language + scenario
                capture.lifetime = .keepAlways
                add(capture)
            }
        }
    }

    func testTimelinePrefixAndForegroundReadKeepTheSameQuestion() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        let answer = app.staticTexts["lio.answer"]
        let step = app.buttons["Next timeline state"]
        let readCount = app.staticTexts["lio.fixture.read-count"]
        XCTAssertTrue(composer.waitForExistence(timeout: 12))
        composer.tap()
        composer.typeText("北京明天天气")
        app.buttons["lio.send"].tap()
        XCTAssertTrue(app.staticTexts["lio.question"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["Lio 正在回复…"].exists)

        step.tap()
        XCTAssertTrue(app.staticTexts["Lio 正在回复…"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["正在查天气…"].exists)
        XCTAssertFalse(answer.exists)

        step.tap()
        XCTAssertTrue(answer.waitForExistence(timeout: 8))
        XCTAssertEqual(answer.label, "北京明天")
        XCTAssertFalse(app.buttons["lio.source"].exists)

        step.tap()
        XCTAssertEqual(answer.label, "北京明天有小雨。")
        XCTAssertFalse(app.buttons["lio.source"].exists)
        XCTAssertFalse(app.staticTexts["演示天气预报"].exists)
        XCTAssertFalse(app.staticTexts["lio.progress"].exists)
        let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        capture.name = "Lio-answer-without-tools"
        capture.lifetime = .keepAlways
        add(capture)

        let before = try XCTUnwrap(Int(readCount.label))
        XCUIDevice.shared.press(.home)
        app.activate()
        let reread = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label != %@", String(before)), object: readCount
        )
        XCTAssertEqual(XCTWaiter.wait(for: [reread], timeout: 8), .completed)
        XCTAssertGreaterThan(try XCTUnwrap(Int(readCount.label)), before)
        XCTAssertEqual(app.staticTexts.matching(identifier: "lio.question").count, 1)
        XCTAssertEqual(answer.label, "北京明天有小雨。")
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")
    }

    func testUnsafeReplyIsWithheldWithoutExposingTools() {
        exerciseWithheldReply("--lio-display-guard")
    }

    func testMarkdownCannotExposeServiceTerms() {
        exerciseWithheldReply("--lio-display-guard-markdown")
        exerciseWithheldReply("--lio-display-guard-host")
        exerciseWithheldReply("--lio-display-guard-wrapped-host")
        exerciseWithheldReply("--lio-display-guard-thought")
        exerciseWithheldReply("--lio-display-guard-tool")
    }

    private func exerciseWithheldReply(_ fixture: String) {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", fixture, "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        XCTAssertTrue(app.staticTexts["lio.answer"].waitForExistence(timeout: 8))
        app.buttons["Next section"].tap()
        let withheld = app.staticTexts["lio.reply.unavailable"]
        XCTAssertTrue(withheld.waitForExistence(timeout: 8))
        XCTAssertEqual(withheld.label, "这条回答暂时无法显示。")
        XCTAssertFalse(app.staticTexts["lio.answer"].exists)
        XCTAssertFalse(app.buttons["lio.source"].exists)
    }

    func testTopControlsCenterLioAndStartANewChat() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let oldReply = app.staticTexts["An earlier reply."]
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        let menu = app.buttons["lio.menu"]
        let name = app.staticTexts["lio.name"]
        let shortcut = app.buttons["lio.chat.newShortcut"]
        XCTAssertTrue(name.exists)
        XCTAssertEqual(name.label, "Lio")
        XCTAssertEqual(name.frame.midX, app.windows.firstMatch.frame.midX, accuracy: 2)
        XCTAssertLessThan(menu.frame.maxX, name.frame.minX)
        XCTAssertGreaterThan(shortcut.frame.minX, name.frame.maxX)
        XCTAssertEqual(menu.frame.midY, shortcut.frame.midY, accuracy: 1)
        XCTAssertEqual(shortcut.label, "New chat")
        // Audit only the top controls; other elements are covered by testEnglish/testChinese.
        let controls: Set<String> = ["lio.name", "lio.chat.newShortcut", "lio.menu"]
        try app.performAccessibilityAudit(for: [.contrast, .hitRegion]) { issue in
            !controls.contains(issue.element?.identifier ?? "")
        }

        XCTAssertTrue(shortcut.isEnabled)
        shortcut.tap()
        XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["lio.opening"].exists)
        XCTAssertFalse(oldReply.exists)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
    }

    func testJumpToLatestReturnsToTheNewestReply() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let jump = app.buttons["lio.jumpToLatest"]
        XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
        XCTAssertFalse(jump.exists)
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        let answers = app.staticTexts.matching(identifier: "lio.answer")
        XCTAssertTrue(answers.firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(jump.exists)
        app.buttons["Next section"].tap()
        let long = answers.containing(NSPredicate(format: "label CONTAINS %@", "Long section.")).firstMatch
        XCTAssertTrue(long.waitForExistence(timeout: 8))

        app.scrollViews.firstMatch.swipeDown()
        app.scrollViews.firstMatch.swipeDown()
        XCTAssertTrue(jump.waitForExistence(timeout: 4))
        XCTAssertEqual(jump.label, "Jump to latest")
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertLessThan(jump.frame.maxY, composer.frame.minY)
        XCTAssertGreaterThan(long.frame.maxY, composer.frame.minY)
        jump.tap()
        let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: jump)
        XCTAssertEqual(XCTWaiter.wait(for: [gone], timeout: 4), .completed)
        XCTAssertLessThanOrEqual(long.frame.maxY, composer.frame.minY)

        app.buttons["Next section"].tap()
        let finished = answers.containing(NSPredicate(format: "label CONTAINS %@", "End of the reply.")).firstMatch
        XCTAssertTrue(finished.waitForExistence(timeout: 8))
        XCTAssertLessThanOrEqual(finished.frame.maxY, composer.frame.minY)
    }

    func testLongPressOffersCopyOnMessages() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", "en", "-AppleLanguages", "(en)"]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        let answer = app.staticTexts["lio.answer"]
        XCTAssertTrue(answer.waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["lio.question"].exists)
        answer.press(forDuration: 1.2)
        XCTAssertTrue(app.menuItems["Copy"].waitForExistence(timeout: 4), app.debugDescription)
    }

    func testLongReplyFollowsUntilTheReaderScrollsAway() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()

        let advance = app.buttons["Next section"]
        let answers = app.staticTexts.matching(identifier: "lio.answer")
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(answers.firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["lio.source"].exists)
        advance.tap()
        let long = answers.containing(NSPredicate(format: "label CONTAINS %@", "Long section.")).firstMatch
        XCTAssertTrue(long.waitForExistence(timeout: 8))
        XCTAssertLessThanOrEqual(long.frame.maxY, composer.frame.minY)
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)

        app.scrollViews.firstMatch.swipeDown()
        let readerPosition = long.frame.minY
        advance.tap()
        let finished = answers.containing(NSPredicate(format: "label CONTAINS %@", "End of the reply.")).firstMatch
        XCTAssertTrue(finished.waitForExistence(timeout: 8))
        XCTAssertEqual(finished.frame.minY, readerPosition, accuracy: 2)
        XCTAssertFalse(app.buttons["lio.source"].exists)
    }

    private func enterSampleQuestion(in app: XCUIApplication, index: Int) {
        let chinese = app.launchArguments.contains("zh-Hans")
        let questions = chinese
            ? ["在上海怎么坐地铁？", "帮我规划北京三天两晚的旅行。"]
            : ["How do I take the metro in Shanghai?", "Plan a three-day trip to Beijing."]
        app.buttons["lio.example.\(index)"].tap()
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        let starter = composer.value as? String ?? ""
        XCTAssertFalse(starter.isEmpty)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        composer.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: starter.count) + questions[index])
        XCTAssertEqual(composer.value as? String, questions[index])
    }

    func testStartersOnlyFillTheComposerInBothLanguages() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for language in ["en", "zh-Hans"] {
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
            app.launch()
            let chinese = language == "zh-Hans"
            let labels = chinese ? ["天气", "景点", "交通", "行程"] : ["Weather", "Sights", "Transport", "Trips"]
            let prefixes = chinese ? ["天气：", "景点：", "交通：", "规划行程："]
                : ["Weather: ", "Sights: ", "Transport: ", "Plan a trip: "]
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(composer.waitForExistence(timeout: 12))
            let first = app.buttons["lio.example.0"]
            let last = app.buttons["lio.example.3"]
            XCTAssertTrue(first.isHittable)
            XCTAssertTrue(last.isHittable)
            XCTAssertEqual(first.frame.midY, last.frame.midY, accuracy: 1)
            let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            capture.name = "Lio-starters-" + language
            capture.lifetime = .keepAlways
            add(capture)
            for index in 0..<4 {
                let button = app.buttons["lio.example.\(index)"]
                XCTAssertEqual(button.label, labels[index])
                button.tap()
                XCTAssertEqual(composer.value as? String, prefixes[index])
                XCTAssertFalse(app.staticTexts["lio.question"].exists)
                XCTAssertFalse(app.staticTexts["lio.answer"].exists)
                XCTAssertTrue(button.exists)
            }
            composer.typeText(chinese ? "北京三天" : "three days in Beijing")
            app.buttons["lio.send"].tap()
            XCTAssertTrue(app.staticTexts["lio.question"].waitForExistence(timeout: 8))
            XCTAssertEqual(app.staticTexts["lio.question"].label,
                           prefixes[3] + (chinese ? "北京三天" : "three days in Beijing"))
            XCTAssertFalse(first.exists)
            XCTAssertFalse(last.exists)
            app.terminate()
        }
    }

    func testRememberedFeedbackStaysWithItsReplyAndFades() throws {
        try exerciseInlineMemoryFeedback(changed: false)
    }

    func testChangedMemoryFeedbackStaysWithItsReply() throws {
        try exerciseInlineMemoryFeedback(changed: true)
    }

    func testLargestMemoryConfirmationKeepsBothActionsReachable() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "-cj.ui.language.v1", language,
                                   "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
            app.launch()
            XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
            let input = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            input.tap(); input.typeText(language == "en" ? "I prefer quiet hotels" : "我喜欢安静的酒店")
            app.buttons["lio.send"].tap()
            let remember = app.buttons["lio.memory.remember"]
            let dismiss = app.buttons["lio.memory.dismiss"]
            XCTAssertTrue(remember.waitForExistence(timeout: 10))
            let jump = app.buttons["lio.jumpToLatest"]
            if jump.waitForExistence(timeout: 2), jump.isHittable { jump.tap() }
            for _ in 0..<8 {
                if dismiss.isHittable && dismiss.frame.maxY <= input.frame.minY { break }
                app.scrollViews.firstMatch.swipeUp()
            }
            XCTAssertTrue(remember.isHittable, app.debugDescription)
            XCTAssertTrue(dismiss.isHittable, app.debugDescription)
            XCTAssertLessThanOrEqual(remember.frame.maxY, dismiss.frame.minY)
            XCTAssertLessThanOrEqual(dismiss.frame.maxY, input.frame.minY)
            XCTAssertGreaterThanOrEqual(remember.frame.width, 44)
            XCTAssertGreaterThanOrEqual(remember.frame.height, 44)
            XCTAssertGreaterThanOrEqual(dismiss.frame.width, 44)
            XCTAssertGreaterThanOrEqual(dismiss.frame.height, 44)
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = language + "-largest-memory-confirmation"
            shot.lifetime = .keepAlways
            add(shot)
            app.terminate()
        }
    }

    private func exerciseInlineMemoryFeedback(changed: Bool) throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let english = language == "en"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "-cj.ui.language.v1", language]
            if changed { app.launchArguments.append("--lio-memory-changed-acceptance") }
            app.launch()
            XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            composer.tap(); composer.typeText(english ? "I prefer quiet hotels" : "我喜欢安静的酒店")
            app.buttons["lio.send"].tap()
            let remember = app.buttons["lio.memory.remember"]
            XCTAssertTrue(remember.waitForExistence(timeout: 10))
            try auditMemoryConfirmation(in: app)
            let followUp = english ? "Any other hotel advice?" : "还有其他酒店建议吗？"
            composer.tap(); composer.typeText(followUp); app.buttons["lio.send"].tap()
            let question = app.staticTexts[followUp]
            XCTAssertTrue(question.waitForExistence(timeout: 8))
            remember.tap()
            let status = app.staticTexts[changed
                ? (english ? "That suggestion changed." : "这条建议已有变化。")
                : (english ? "Remembered" : "已记住")]
            XCTAssertTrue(status.waitForExistence(timeout: 10), app.debugDescription)
            XCTAssertLessThan(status.frame.maxY, question.frame.minY)
            XCTAssertFalse(remember.exists)
            if !changed {
                let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: status)
                XCTAssertEqual(XCTWaiter.wait(for: [gone], timeout: 5), .completed)
                XCTAssertFalse(remember.exists)
            }
            app.terminate()
        }
    }

    private func auditMemoryConfirmation(in app: XCUIApplication) throws {
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: String(describing: issue.auditType) + "\n" +
                                       (issue.element?.debugDescription ?? "No element supplied by audit"))
            detail.name = "Card and memory AX issue"
            detail.lifetime = .keepAlways
            self.add(detail)
            return false
        }
    }

    private func exercise(_ language: String, question: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
        XCTAssertTrue(app.staticTexts["Lio"].exists)
        let greeting = app.staticTexts["lio.opening"]
        XCTAssertTrue(greeting.exists)
        XCTAssertEqual(greeting.label, language == "en" ? "Hi, I'm Lio. Tell me the city, how many days you have and what you enjoy, and I'll plan where to go and how to get around each day. Where are you headed?"
                       : "你好，我是 Lio。告诉我城市、天数和喜好，我帮你排好每天去哪、怎么走。这次想去哪儿？")
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        XCTAssertFalse(app.navigationBars.firstMatch.exists)
        XCTAssertTrue(app.tabBars.buttons[language == "en" ? "Trips" : "行程"].exists)
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.isHittable)
        try app.performAccessibilityAudit(for: .all)

        enterSampleQuestion(in: app, index: 0)
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertEqual(composer.value as? String, question)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        XCTAssertTrue(app.buttons["lio.send"].isEnabled)
        app.buttons["lio.send"].tap()

        let sentQuestion = app.staticTexts["lio.question"]
        let answer = app.staticTexts["lio.answer"]
        XCTAssertTrue(sentQuestion.waitForExistence(timeout: 8))
        XCTAssertTrue(answer.waitForExistence(timeout: 8))
        XCTAssertLessThan(answer.frame.minX, sentQuestion.frame.minX)
        XCTAssertGreaterThanOrEqual(answer.frame.minY, sentQuestion.frame.maxY)
        XCTAssertFalse(app.buttons["lio.source"].exists)
        XCTAssertFalse(app.staticTexts["lio.progress"].exists)
        XCTAssertFalse(app.navigationBars.firstMatch.exists)
        XCTAssertFalse(app.links.firstMatch.exists)
    }
}
