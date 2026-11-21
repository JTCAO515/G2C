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
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "插件"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                app.buttons["lio.tools.translation"].tap()
                XCTAssertTrue(app.buttons["lio.translation.swap"].waitForExistence(timeout: 6))

                for mode in ["text", "voice", "photo"] {
                    app.buttons["lio.translation.mode.\(mode)"].tap()
                    try app.performAccessibilityAudit(for: .all)
                    let screenshot = XCTAttachment(screenshot: app.screenshot())
                    screenshot.name = "translation-\(mode)-\(language)-\(appearance)"
                    screenshot.lifetime = .keepAlways
                    add(screenshot)
                }

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
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "插件"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                app.buttons["lio.tools.translation"].tap()
                XCTAssertTrue(app.buttons["lio.translation.swap"].waitForExistence(timeout: 6))
                XCTAssertTrue(app.textViews["lio.translation.input"].isHittable)
                for mode in ["text", "voice", "photo"] {
                    XCTAssertTrue(app.buttons["lio.translation.mode.\(mode)"].isHittable)
                }

                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "translation-maximum-size-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)

                app.buttons["lio.translation.mode.photo"].tap()
                XCTAssertTrue(app.buttons["lio.translation.camera"].isHittable)
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

        let voiceMode = app.buttons["lio.translation.mode.voice"]
        XCTAssertTrue(voiceMode.waitForExistence(timeout: 5))
        voiceMode.tap()
        XCTAssertTrue(app.buttons["lio.translation.voice"].isHittable)
        XCTAssertFalse(editor.exists)

        app.buttons["lio.translation.mode.photo"].tap()
        XCTAssertTrue(app.buttons["lio.translation.camera"].isHittable)
        XCTAssertTrue(app.buttons["lio.translation.photo"].isHittable)
        XCTAssertFalse(app.buttons["lio.translation.voice"].exists)

        app.buttons["lio.translation.mode.text"].tap()
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
        let translate = app.buttons["lio.translation.submit"]
        let initialFrame = translate.frame
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
            XCTAssertEqual(translate.frame.origin.x, initialFrame.origin.x, accuracy: 1)
            XCTAssertEqual(translate.frame.origin.y, initialFrame.origin.y, accuracy: 1)
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
        editor.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0.25))
            .withOffset(CGVector(dx: -8, dy: 0)).tap()
        expectDismissed()

        editor.tap()
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        let scroller = app.scrollViews["lio.translation.scroll"]
        XCTAssertTrue(scroller.exists)
        let belowEditor = editor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 1))
            .withOffset(CGVector(dx: 0, dy: 5))
        let aboveEditor = editor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0))
            .withOffset(CGVector(dx: 0, dy: -5))
        belowEditor.press(forDuration: 0.05, thenDragTo: aboveEditor)
        expectDismissed()
        XCTAssertEqual(editor.value as? String, "Keep this draft")
    }
}
