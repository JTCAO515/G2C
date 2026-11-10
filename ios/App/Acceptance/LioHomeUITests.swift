import XCTest

@MainActor final class LioHomeUITests: XCTestCase {
    func testEnglish() throws { try exercise("en", question: "How do I take the metro in Shanghai?", source: "Source") }
    func testChinese() throws { try exercise("zh-Hans", question: "在上海怎么坐地铁？", source: "来源") }

    func testInvitationEnglish() throws { try exerciseInvitation("en") }
    func testInvitationChinese() throws { try exerciseInvitation("zh-Hans") }

    func testNewChatAndHistoryKeepMessagesAndDraftsSeparate() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let menu = app.buttons["lio.menu"]
        let oldReply = app.staticTexts["An earlier reply."]
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        menu.tap()
        app.buttons["lio.chat.new"].tap()
        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        XCTAssertFalse(oldReply.exists)
        example.tap()
        let draft = "How do I take the metro in Shanghai?"
        XCTAssertEqual(composer.value as? String, draft)

        func openHistory(_ title: String) {
            menu.tap()
            app.buttons["lio.chat.history"].tap()
            let row = app.buttons.matching(identifier: "lio.chat.history.row")
                .matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 8))
            row.tap()
        }
        openHistory("Earlier conversation")
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        XCTAssertNotEqual(composer.value as? String, draft)
        openHistory("New conversation")
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        XCTAssertFalse(oldReply.exists)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
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
        metro.tap()
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        send.tap()
        XCTAssertTrue(app.staticTexts[chinese ? "正在查旅行信息…" : "Checking travel information…"]
            .waitForExistence(timeout: 3))
        reply(chinese ? "跟着地铁线路指示牌走。" : "Follow the signs for your metro line.")
        let source = app.buttons["lio.source"]
        XCTAssertTrue(source.waitForExistence(timeout: 6))
        source.tap()
        let sourceTitle = chinese ? "来源" : "Source"
        XCTAssertTrue(app.navigationBars[sourceTitle].waitForExistence(timeout: 6))
        app.navigationBars[sourceTitle].buttons[chinese ? "完成" : "Done"].tap()

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

    private func exerciseTrip(_ language: String, clarification: String, trips: String, day: String, fixed: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.1"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        sample.tap()
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
        sample.tap()
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
        let quota = app.staticTexts.containing(NSPredicate(format: "label == %@", "今天的 40 个问题已用完，明天再来聊吧。"))
            .firstMatch
        XCTAssertTrue(quota.waitForExistence(timeout: 8))
        XCTAssertEqual(questions.count, 1)
        XCTAssertEqual(questions.firstMatch.label, "在上海怎么坐地铁？")
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "2")
        XCTAssertFalse(resend.exists)
        XCTAssertFalse(app.buttons["lio.askAgain"].exists)
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
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label BEGINSWITH %@", "思考中")).firstMatch.exists)

        step.tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label BEGINSWITH %@", "正在查天气"))
            .firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(answer.exists)

        step.tap()
        XCTAssertTrue(answer.waitForExistence(timeout: 8))
        XCTAssertEqual(answer.label, "北京明天")
        XCTAssertFalse(app.buttons["lio.source"].exists)

        step.tap()
        let source = app.buttons["lio.source"]
        XCTAssertTrue(source.waitForExistence(timeout: 8))
        XCTAssertEqual(answer.label, "北京明天有小雨。")
        source.tap()
        XCTAssertTrue(app.navigationBars["来源"].waitForExistence(timeout: 8))
        let openSource = app.descendants(matching: .any).matching(identifier: "打开来源").firstMatch
        XCTAssertTrue(openSource.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertTrue(openSource.isHittable, app.debugDescription)
        XCTAssertFalse(app.staticTexts["这条来源没有链接。"].exists)
        app.navigationBars["来源"].buttons["完成"].tap()

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

    func testUnsafeReplyIsWithheldWithoutHidingTheAttribution() {
        exerciseWithheldReply("--lio-display-guard")
    }

    func testMarkdownCannotExposeServiceTerms() {
        exerciseWithheldReply("--lio-display-guard-markdown")
        exerciseWithheldReply("--lio-display-guard-host")
    }

    private func exerciseWithheldReply(_ fixture: String) {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", fixture, "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        sample.tap()
        app.buttons["lio.send"].tap()
        XCTAssertTrue(app.staticTexts["lio.answer"].waitForExistence(timeout: 8))
        app.buttons["Next section"].tap()
        let withheld = app.staticTexts["lio.reply.unavailable"]
        XCTAssertTrue(withheld.waitForExistence(timeout: 8))
        XCTAssertEqual(withheld.label, "这条回答暂时无法显示。")
        XCTAssertFalse(app.staticTexts["lio.answer"].exists)
        XCTAssertTrue(app.buttons["lio.source"].exists)
    }

    func testLongReplyFollowsUntilTheReaderScrollsAway() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        sample.tap()
        app.buttons["lio.send"].tap()

        let source = app.buttons["lio.source"]
        let advance = app.buttons["Next section"]
        let answers = app.staticTexts.matching(identifier: "lio.answer")
        XCTAssertTrue(source.waitForExistence(timeout: 8))
        XCTAssertTrue(source.isHittable)
        advance.tap()
        let long = answers.containing(NSPredicate(format: "label CONTAINS %@", "Long section.")).firstMatch
        XCTAssertTrue(long.waitForExistence(timeout: 8))
        XCTAssertTrue(source.isHittable)
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)

        app.scrollViews.firstMatch.swipeDown()
        XCTAssertFalse(source.isHittable)
        advance.tap()
        let finished = answers.containing(NSPredicate(format: "label CONTAINS %@", "End of the reply.")).firstMatch
        XCTAssertTrue(finished.waitForExistence(timeout: 8))
        XCTAssertFalse(source.isHittable)
    }

    private func exercise(_ language: String, question: String, source title: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
        XCTAssertTrue(app.staticTexts["Lio"].exists)
        XCTAssertFalse(app.navigationBars.firstMatch.exists)
        XCTAssertTrue(app.tabBars.buttons[language == "en" ? "Trips" : "行程"].exists)
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.isHittable)
        try app.performAccessibilityAudit(for: .all)

        sample.tap()
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertEqual(composer.value as? String, question)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        XCTAssertTrue(app.buttons["lio.send"].isEnabled)
        app.buttons["lio.send"].tap()

        XCTAssertTrue(app.staticTexts["lio.question"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["lio.answer"].waitForExistence(timeout: 8))
        let source = app.buttons["lio.source"]
        XCTAssertTrue(source.waitForExistence(timeout: 8))
        XCTAssertTrue(source.isHittable)
        source.tap()
        XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 8))
        XCTAssertFalse(app.links.firstMatch.exists)
    }
}
