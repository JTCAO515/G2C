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

    @objc func testToolsPhotoPickerShowsOriginalLinesOnIOS17() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en",
                               "-AppleLanguages", "(en)"]
        app.launch()
        defer { app.terminate() }
        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.translation"].tap()
        let photo = app.buttons["lio.translation.photo"]
        XCTAssertTrue(photo.waitForExistence(timeout: 6))
        photo.tap()
        let fixture = app.images.matching(NSPredicate(format: "label BEGINSWITH %@", "Photo,")).firstMatch
        XCTAssertTrue(fixture.waitForExistence(timeout: 8), app.debugDescription)
        fixture.tap()
        let original = app.staticTexts["lio.translation.image-text"]
        XCTAssertTrue(original.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertEqual(original.label, "Tea\nCoffee")
        let problem = app.staticTexts["lio.translation.problem"]
        XCTAssertTrue(problem.exists)
        XCTAssertTrue(problem.label.contains("iOS 18"))
    }
}
