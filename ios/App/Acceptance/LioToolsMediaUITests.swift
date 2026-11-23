import XCTest

@MainActor extension LioToolsUITests {
    // Run only on an isolated simulator with microphone access explicitly denied.
    @objc func testToolsMicrophoneDenialKeepsTranslationOpen() {
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
        app.buttons["lio.translation.mode.voice"].tap()
        let voice = app.buttons["lio.translation.voice"]
        XCTAssertTrue(voice.waitForExistence(timeout: 6))
        voice.tap()
        let message = app.staticTexts["Allow microphone access in Settings to use voice input."]
        XCTAssertTrue(message.waitForExistence(timeout: 6))
        XCTAssertTrue(app.buttons["Open Settings"].exists)
        XCTAssertEqual(app.state, .runningForeground)
        voice.tap()
        XCTAssertTrue(message.waitForExistence(timeout: 6))
        XCTAssertFalse(app.staticTexts["lio.translation.transcript"].exists)
        app.buttons["lio.translation.mode.text"].tap()
        XCTAssertTrue(app.textViews["lio.translation.input"].exists)
    }

    @objc func testToolsUnavailableSimulatorCameraKeepsPhotoPickerAvailable() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language]
            app.launch()
            app.tabBars.buttons[language == "en" ? "Tools" : "插件"].tap()
            app.buttons["lio.tools.translation"].tap()
            app.buttons["lio.translation.mode.photo"].tap()
            let camera = app.buttons["lio.translation.camera"]
            XCTAssertTrue(camera.waitForExistence(timeout: 6))
            camera.tap()
            XCTAssertTrue(app.staticTexts["lio.translation.image-problem"].waitForExistence(timeout: 6))
            XCTAssertTrue(app.buttons["lio.translation.photo"].isEnabled)
            app.terminate()
        }
    }
}

@MainActor extension LioToolsUITests {
    @objc func testPhotoLayoutFixtureSwitchesOriginalTranslationAndLines() throws {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-photo-layout-preview",
                               "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.translation"].tap()
        app.buttons["lio.translation.mode.photo"].tap()
        let preview = app.buttons["lio.translation.photo-layout.preview"]
        XCTAssertTrue(preview.waitForExistence(timeout: 5))
        preview.tap()

        let photo = app.images["lio.translation.photo-layout.image"]
        XCTAssertTrue(photo.waitForExistence(timeout: 5))
        XCTAssertEqual(photo.label, "Translated photo")
        app.buttons["Original"].tap()
        XCTAssertEqual(photo.label, "Original photo")
        app.buttons["Line by line"].tap()
        let line = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@", "咖啡", "Coffee"))
        XCTAssertTrue(line.firstMatch.exists)
        try app.performAccessibilityAudit(for: .all)
    }
}
