import XCTest

@MainActor extension LioToolsUITests {
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

    @objc func testSOSOpensEmergencyNumbersDuringChatAndRecovery() throws {
        continueAfterFailure = false
        for (arguments, hasNewChat) in [
            (["--lio-chat-history-acceptance", "--lio-support-sos"], true),
            (["--lio-chat-history-acceptance", "--lio-support-sos", "--lio-support-suspended"], false),
            (["--lio-session-recovery-acceptance", "--lio-support-sos"], false),
        ] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", "en"] + arguments
            app.launch()
            defer { app.terminate() }
            let sos = app.buttons["lio.support.sos"]
            XCTAssertTrue(sos.waitForExistence(timeout: 10))
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
        }
    }
}
