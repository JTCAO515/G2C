import XCTest

@MainActor extension LioToolsUITests {
    @objc func testTranslationCardsAndHistoryPassFullAudit() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance]
                app.launch()
                defer { app.terminate() }
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "工具"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                app.buttons["lio.tools.translation"].tap()
                XCTAssertTrue(app.buttons["lio.translation.swap"].waitForExistence(timeout: 6))

                // One page (#1421): text field, hold-to-talk microphone and camera menu share the bar.
                XCTAssertTrue(app.textViews["lio.translation.input"].isHittable)
                XCTAssertTrue(app.buttons["lio.translation.voice"].isHittable)
                XCTAssertTrue(app.buttons["lio.translation.camera-menu"].isHittable)
                XCTAssertFalse(app.buttons["lio.translation.mode.text"].exists)
                try app.performAccessibilityAudit(for: .all)
                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "translation-page-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)
                app.buttons["lio.translation.camera-menu"].tap()
                XCTAssertTrue(app.buttons["lio.translation.camera"].waitForExistence(timeout: 5))
                XCTAssertTrue(app.buttons["lio.translation.photo"].exists)
                try app.performAccessibilityAudit(for: .all)
                app.buttons["lio.translation.camera-menu"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
                    .withOffset(CGVector(dx: 0, dy: -300)).tap()

                app.navigationBars.buttons["lio.translation.history"].tap()
                let close = app.navigationBars.buttons["lio.translation.history-close"]
                XCTAssertTrue(close.waitForExistence(timeout: 5))
                try app.performAccessibilityAudit(for: .all)
                close.tap()
            }
        }
    }

    @objc func testTranslationMaximumTextSizeInBothLanguagesAndAppearances() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                       "UICTContentSizeCategoryAccessibilityXXXL"]
                app.launch()
                defer { app.terminate() }
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "工具"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                app.buttons["lio.tools.translation"].tap()
                XCTAssertTrue(app.buttons["lio.translation.swap"].waitForExistence(timeout: 6))
                XCTAssertTrue(app.textViews["lio.translation.input"].isHittable)
                XCTAssertTrue(app.buttons["lio.translation.voice"].isHittable)
                XCTAssertTrue(app.buttons["lio.translation.camera-menu"].isHittable)

                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "translation-maximum-size-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)

                app.buttons["lio.translation.camera-menu"].tap()
                XCTAssertTrue(app.buttons["lio.translation.camera"].waitForExistence(timeout: 5))
                XCTAssertTrue(app.buttons["lio.translation.photo"].isHittable)
            }
        }
    }

    @objc func testTranslationModesAndHistoryPreserveTextDraft() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-translation-relay-preview",
                               "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.translation"].tap()
        let editor = app.textViews["lio.translation.input"]
        XCTAssertTrue(editor.waitForExistence(timeout: 6))
        editor.tap()
        editor.typeText("Hello")
        app.navigationBars.buttons["lio.translation.keyboard-done"].tap()

        // With typed text the microphone gives way to the send arrow; the camera menu stays.
        XCTAssertTrue(app.buttons["lio.translation.submit"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["lio.translation.voice"].exists)
        app.buttons["lio.translation.camera-menu"].tap()
        XCTAssertTrue(app.buttons["lio.translation.camera"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["lio.translation.photo"].isHittable)
        app.buttons["lio.translation.camera-menu"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .withOffset(CGVector(dx: 0, dy: -300)).tap()

        XCTAssertEqual(editor.value as? String, "Hello")
        app.buttons["lio.translation.submit"].tap()
        let result = app.staticTexts["lio.translation.result"]
        XCTAssertTrue(result.waitForExistence(timeout: 6))
        XCTAssertEqual(result.label, "你好")
        app.navigationBars.buttons["lio.translation.history"].tap()
        let close = app.navigationBars.buttons["lio.translation.history-close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5))
        close.tap()
        XCTAssertEqual(editor.value as? String, "Hello")
        XCTAssertEqual(result.label, "你好")
    }

    @objc func testTranslationKeyboardDismissesWithoutMovingThePageControls() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.translation"].tap()
        let editor = app.textViews["lio.translation.input"]
        XCTAssertTrue(editor.waitForExistence(timeout: 6))
        // The input bar follows the keyboard like a chat composer (#1421) and returns when it closes.
        let camera = app.buttons["lio.translation.camera-menu"]
        let initialFrame = camera.frame
        let keyboard = app.keyboards.firstMatch
        let done = app.navigationBars.buttons["lio.translation.keyboard-done"]

        func capture(_ name: String) {
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = name
            shot.lifetime = .keepAlways
            add(shot)
        }
        func expectDismissed() {
            let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: keyboard)
            XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 5), .completed)
            XCTAssertFalse(done.exists)
            XCTAssertEqual(camera.frame.origin.x, initialFrame.origin.x, accuracy: 1)
            XCTAssertEqual(camera.frame.origin.y, initialFrame.origin.y, accuracy: 1)
        }

        capture("translation-before-editing")
        editor.tap()
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        editor.typeText("Keep this draft")
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        capture("translation-keyboard-and-done")
        done.tap()
        expectDismissed()
        XCTAssertEqual(editor.value as? String, "Keep this draft")
        capture("translation-after-done")

        editor.tap()
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        editor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0))
            .withOffset(CGVector(dx: 0, dy: -120)).tap()
        expectDismissed()

        editor.tap()
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        let scroller = app.scrollViews["lio.translation.scroll"]
        XCTAssertTrue(scroller.exists)
        let lower = scroller.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))
        let upper = scroller.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.15))
        lower.press(forDuration: 0.05, thenDragTo: upper)
        expectDismissed()
        XCTAssertEqual(editor.value as? String, "Keep this draft")
    }
}
