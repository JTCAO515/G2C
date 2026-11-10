import XCTest

@MainActor final class LioHomeUITests: XCTestCase {
    func testEnglish() throws { try exercise("en", question: "How do I take the metro in Shanghai?", source: "Source") }
    func testChinese() throws { try exercise("zh-Hans", question: "在上海怎么坐地铁？", source: "来源") }

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
        XCTAssertFalse(app.tabBars.firstMatch.exists)
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
