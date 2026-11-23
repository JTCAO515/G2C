import XCTest

@MainActor extension LioToolsUITests {
    @objc func testLocalAddressFixtureShowsChineseAddressAndFailureStates() throws {
        continueAfterFailure = false
        for scenario in ["address", "denied", "offline"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-where-am-i-preview",
                                   "-cj.ui.language.v1", "en", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
            if scenario != "address" { app.launchArguments += ["--lio-where-am-i-" + scenario] }
            app.launch()
            defer { app.terminate() }
            openLocalSupport(app)
            let entry = app.buttons["lio.support.where-am-i"]
            for _ in 0..<6 where !entry.isHittable { app.swipeUp() }
            XCTAssertTrue(entry.isHittable)
            entry.tap()
            app.buttons["lio.support.location.lookup"].tap()
            if scenario == "address" {
                let address = app.staticTexts["lio.support.location.address"]
                XCTAssertTrue(address.waitForExistence(timeout: 6))
                XCTAssertEqual(address.label, "北京市示例大道1号")
                XCTAssertTrue(app.buttons["lio.support.location.copy"].exists)
            } else {
                let problem = app.staticTexts["lio.support.location.problem"]
                XCTAssertTrue(problem.waitForExistence(timeout: 6))
                XCTAssertTrue(problem.label.contains(scenario == "denied" ? "Location access is off" : "Connect to the internet"))
                XCTAssertFalse(app.staticTexts["lio.support.location.address"].exists)
            }
            try app.performAccessibilityAudit(for: .all)
        }
    }

    @objc func testLocalSupportListsPhonesWithoutCallingInBothLanguagesAndAppearances() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance]
                app.launch()
                defer { app.terminate() }
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "插件"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                let support = app.buttons["lio.tools.local-support"]
                let translation = app.buttons["lio.tools.translation"]
                XCTAssertTrue(support.waitForExistence(timeout: 6))
                XCTAssertLessThan(support.frame.minY, translation.frame.minY)
                support.tap()
                for (id, number) in [("police", "110"), ("ambulance", "120"), ("fire", "119"), ("traffic", "122")] {
                    let tile = app.buttons["lio.support." + id]
                    XCTAssertTrue(tile.exists)
                    XCTAssertTrue(tile.label.contains(number))
                    XCTAssertGreaterThanOrEqual(tile.frame.height, 44)
                }
                XCTAssertTrue(app.staticTexts["12367"].exists)
                let city = app.buttons["lio.support.city"]
                XCTAssertGreaterThanOrEqual(city.frame.width, 44)
                XCTAssertGreaterThanOrEqual(city.frame.height, 44)
                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "local-support-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)
                try app.performAccessibilityAudit(for: .all)
            }
        }
    }

    @objc func testLocalSupportSearchesNationalitiesAndRestoresOnlyTheSelectedEmbassy() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        openLocalSupport(app)
        showNationalityButton(in: app).tap()
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 5))
        search.tap()
        search.typeText("Japan")
        let japan = app.buttons["lio.support.country.JP"]
        XCTAssertTrue(japan.waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["lio.support.country.KR"].exists)
        japan.tap()
        showNationalityButton(in: app)
        XCTAssertTrue(app.staticTexts["Embassy of Japan"].exists)
        XCTAssertTrue(app.buttons["lio.support.embassy.copy-address"].exists)
        XCTAssertTrue(app.buttons["lio.support.embassy.open-map"].exists)
        XCTAssertFalse(app.staticTexts["Embassy of the Republic of Korea"].exists)
        app.terminate()
        app.launch()
        openLocalSupport(app)
        showNationalityButton(in: app)
        XCTAssertTrue(app.staticTexts["Embassy of Japan"].exists)
        XCTAssertFalse(app.staticTexts["Embassy of the Republic of Korea"].exists)
    }

    @objc func testLocalSupportExplainsWhenNoEmbassyMatches() {
        continueAfterFailure = false
        for (language, copy) in [
            ("en", "No matching embassies. Try another country name."),
            ("zh-Hans", "没有找到匹配的使馆，请换一个国家名称。"),
        ] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                   "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
            app.launch()
            defer { app.terminate() }
            openLocalSupport(app, language: language)
            showNationalityButton(in: app).tap()

            let search = app.searchFields.firstMatch
            XCTAssertTrue(search.waitForExistence(timeout: 5))
            search.tap()
            search.typeText("zzzzzxzzzz")
            let empty = app.staticTexts["lio.support.country.no-results"]
            XCTAssertTrue(empty.waitForExistence(timeout: 5))
            XCTAssertEqual(empty.label, copy)
            XCTAssertFalse(app.buttons["lio.support.country.JP"].exists)
        }
    }

    private func openLocalSupport(_ app: XCUIApplication, language: String = "en") {
        let tools = app.tabBars.buttons[language == "en" ? "Tools" : "插件"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        let support = app.buttons["lio.tools.local-support"]
        XCTAssertTrue(support.waitForExistence(timeout: 6))
        support.tap()
    }

    @discardableResult
    private func showNationalityButton(in app: XCUIApplication) -> XCUIElement {
        let button = app.buttons["lio.support.nationality"]
        for _ in 0..<5 where !button.isHittable {
            app.scrollViews.firstMatch.swipeUp()
        }
        XCTAssertTrue(button.isHittable)
        return button
    }

    @objc func testLocalSupportDraftReopensAndClearsWithoutSending() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en"]
        app.launchEnvironment["G2C_LIO_SUPPORT_DRAFT_FIXTURE"] = UUID().uuidString
        let editor = app.descendants(matching: .any).matching(identifier: "lio.support.draft").firstMatch

        func openDraft() {
            app.launch()
            let tools = app.tabBars.buttons["Tools"]
            XCTAssertTrue(tools.waitForExistence(timeout: 8))
            tools.tap()
            app.buttons["lio.tools.local-support"].tap()
            for _ in 0..<5 where !editor.isHittable { app.swipeUp() }
            XCTAssertTrue(editor.isHittable)
            let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: editor)
            XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        }

        openDraft()
        editor.tap()
        editor.typeText("Need help\nSecond line")
        XCTAssertEqual(editor.value as? String, "Need help\nSecond line")
        let send = app.buttons["lio.support.send"]
        XCTAssertTrue(send.exists)
        XCTAssertFalse(send.isEnabled)

        app.terminate()
        openDraft()
        XCTAssertEqual(editor.value as? String, "Need help\nSecond line")
        let clear = app.buttons["lio.support.draft-clear"]
        for _ in 0..<3 where !clear.isHittable { app.swipeUp() }
        XCTAssertTrue(clear.isHittable)
        clear.tap()

        app.terminate()
        openDraft()
        XCTAssertNotEqual(editor.value as? String, "Need help\nSecond line")
        XCTAssertFalse(app.buttons["lio.support.draft-clear"].isEnabled)
        app.terminate()
    }

    @objc func testLocalSupportDraftRejectsOverflowAtLargestTextSize() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en", "-UIPreferredContentSizeCategoryName",
                               "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launchEnvironment["G2C_LIO_SUPPORT_DRAFT_FIXTURE"] = UUID().uuidString
        let editor = app.descendants(matching: .any).matching(identifier: "lio.support.draft").firstMatch

        func openDraft() {
            app.launch()
            openLocalSupport(app)
            for _ in 0..<16 where !editor.isHittable { app.swipeUp() }
            XCTAssertTrue(editor.isHittable)
            let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: editor)
            XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 5), .completed)
        }

        openDraft()
        editor.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        editor.typeText("Need help\nSecond line")
        XCTAssertEqual(editor.value as? String, "Need help\nSecond line")
        let send = app.buttons["lio.support.send"]
        XCTAssertTrue(send.exists)
        XCTAssertFalse(send.isEnabled)

        app.terminate()
        openDraft()
        let initial = "Need help\nSecond line"
        XCTAssertEqual(editor.value as? String, initial)
        editor.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        editor.typeText(String(repeating: "a", count: 1000 - initial.count))
        let maximum = try XCTUnwrap(editor.value as? String)
        XCTAssertEqual(maximum.count, 1000)
        XCTAssertEqual(maximum.replacingOccurrences(of: "a", with: ""), initial)
        editor.typeText("z")
        XCTAssertEqual(editor.value as? String, maximum)
        XCTAssertTrue(app.staticTexts["lio.support.draft-message"].exists)
        app.terminate()
        openDraft()
        XCTAssertEqual(editor.value as? String, maximum)
        let clear = app.buttons["lio.support.draft-clear"]
        let directory = app.scrollViews.firstMatch
        for _ in 0..<6 where !clear.isHittable {
            // Drag beside the text field to scroll the page, not the long draft.
            let start = directory.coordinate(withNormalizedOffset: CGVector(dx: 0.025, dy: 0.82))
            let end = directory.coordinate(withNormalizedOffset: CGVector(dx: 0.025, dy: 0.30))
            start.press(forDuration: 0.05, thenDragTo: end)
        }
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "largest-support-draft-clear"
        attachment.lifetime = .keepAlways
        add(attachment)
        XCTAssertTrue(clear.isHittable)
        clear.tap()

        app.terminate()
        openDraft()
        XCTAssertNotEqual(editor.value as? String, maximum)
        XCTAssertFalse(app.buttons["lio.support.draft-clear"].isEnabled)
        app.terminate()
    }

    @objc func testSOSOpensEmergencyNumbersDuringChatAndRecovery() throws {
        continueAfterFailure = false
        for (index, (arguments, hasNewChat, showConnectionError)) in [
            (["--lio-chat-history-acceptance", "--lio-support-sos"], true, false),
            (["--lio-chat-history-acceptance", "--lio-support-sos", "--lio-support-suspended"], false, false),
            (["--lio-session-recovery-acceptance", "--lio-support-sos"], false, false),
            (["--lio-session-recovery-acceptance", "--lio-support-sos"], false, true),
            (["--lio-onboarding-preview", "--lio-support-sos"], false, false),
        ].enumerated() {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", "en"] + arguments
            app.launch()
            defer { app.terminate() }
            let sos = app.buttons["lio.support.sos"]
            XCTAssertTrue(sos.waitForExistence(timeout: 10))
            if showConnectionError {
                app.buttons["synthetic.recovery.offline"].tap()
            }
            XCTAssertTrue(sos.isEnabled)
            if hasNewChat {
                let newChat = app.buttons["lio.chat.newShortcut"]
                XCTAssertTrue(newChat.exists)
                XCTAssertLessThan(sos.frame.midX, newChat.frame.midX)
                try app.performAccessibilityAudit(for: .all)
            }
            sos.tap()
            XCTAssertTrue(app.staticTexts["Emergency numbers"].waitForExistence(timeout: 6))
            XCTAssertTrue(app.buttons["lio.support.police"].label.contains("110"))
            let attachment = XCTAttachment(screenshot: app.screenshot())
            attachment.name = "sos-sheet-state-\(index)"
            attachment.lifetime = .keepAlways
            add(attachment)
            try app.performAccessibilityAudit(for: .all)
            let close = app.buttons["Close"]
            XCTAssertTrue(close.isHittable)
            XCTAssertGreaterThanOrEqual(close.frame.height, 44)
            XCTAssertGreaterThanOrEqual(close.frame.width, 44)
            close.tap()
            XCTAssertTrue(sos.waitForExistence(timeout: 6))
            XCTAssertFalse(app.staticTexts["Emergency numbers"].exists)
        }
    }

    @objc func testLocalSupportShowsConsumerContactsAtLargestTextSize() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en",
                               "-lio.ui.appearance.v1", "dark", "-UIPreferredContentSizeCategoryName",
                               "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        defer { app.terminate() }
        openLocalSupport(app)
        try app.performAccessibilityAudit(for: .all)
        let consumer = app.buttons["lio.support.consumer"]
        for _ in 0..<12 where !consumer.isHittable {
            app.scrollViews.firstMatch.swipeUp()
        }
        XCTAssertTrue(consumer.isHittable)
        XCTAssertTrue(app.staticTexts["12315"].exists)
        XCTAssertGreaterThanOrEqual(consumer.frame.height, 44)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "local-support-largest-text"
        screenshot.lifetime = .keepAlways
        add(screenshot)
        try app.performAccessibilityAudit(for: .all)
    }

    @objc func testDebugDialUsesTheConfiguredNumberWithoutCalling() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-support-dial-preview",
                               "-cj.ui.language.v1", "en"]
        app.launchEnvironment["G2C_LOCAL_SUPPORT_TEST_PHONE"] = "__LOCAL_SUPPORT_TEST_PHONE__"
        app.launch()
        defer { app.terminate() }

        let ready = app.staticTexts["fixture.support.dial-intercept-ready"]
        XCTAssertTrue(ready.waitForExistence(timeout: 8))
        app.tabBars.buttons["Tools"].tap()
        app.buttons["lio.tools.local-support"].tap()
        let dial = app.buttons["lio.support.test-dial"]
        for _ in 0..<5 where !dial.isHittable { app.swipeUp() }
        XCTAssertTrue(dial.isHittable)
        dial.tap()
        XCTAssertTrue(app.staticTexts["fixture.support.dial-matched"].waitForExistence(timeout: 6))
    }
}
