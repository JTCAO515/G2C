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
        XCTAssertTrue(app.textViews["lio.translation.input"].exists)
    }

    @objc func testToolsUnavailableSimulatorCameraKeepsPhotoPickerAvailable() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language]
            app.launch()
            app.tabBars.buttons[language == "en" ? "Tools" : "工具"].tap()
            app.buttons["lio.tools.translation"].tap()
            app.buttons["lio.translation.camera-menu"].tap()
            let camera = app.buttons["lio.translation.camera"]
            XCTAssertTrue(camera.waitForExistence(timeout: 6))
            camera.tap()
            XCTAssertTrue(app.descendants(matching: .any)["lio.translation.input-notice"].waitForExistence(timeout: 6))
            app.buttons["lio.translation.camera-menu"].tap()
            XCTAssertTrue(app.buttons["lio.translation.photo"].waitForExistence(timeout: 6))
            XCTAssertTrue(app.buttons["lio.translation.photo"].isEnabled)
            app.terminate()
        }
    }
}
