import XCTest

@MainActor extension LioToolsUITests {
    @objc func testToolsUnavailableSimulatorCameraKeepsPhotoPickerAvailable() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language]
            app.launch()
            app.tabBars.buttons[language == "en" ? "Tools" : "插件"].tap()
            app.buttons["lio.tools.translation"].tap()
            let camera = app.buttons["lio.translation.camera"]
            XCTAssertTrue(camera.waitForExistence(timeout: 6))
            camera.tap()
            XCTAssertTrue(app.staticTexts["lio.translation.image-problem"].waitForExistence(timeout: 6))
            XCTAssertTrue(app.buttons["lio.translation.photo"].isEnabled)
            app.terminate()
        }
    }
}
