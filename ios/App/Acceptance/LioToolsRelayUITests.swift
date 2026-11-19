import XCTest

@MainActor extension LioToolsUITests {
    // Run on the dedicated simulator seeded with the two-line synthetic menu as its newest photo.
    @objc func testToolsPhotoPickerPairsRelayFixtureLinesOnIOS17() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-translation-relay-preview",
                               "-cj.ui.language.v1", "en", "-AppleLanguages", "(en)"]
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
        let first = app.descendants(matching: .any).matching(identifier: "lio.translation.line.0").firstMatch
        let second = app.descendants(matching: .any).matching(identifier: "lio.translation.line.1").firstMatch
        XCTAssertTrue(first.waitForExistence(timeout: 10), app.debugDescription)
        XCTAssertTrue(first.label.contains("Tea") && first.label.contains("茶"), first.debugDescription)
        XCTAssertTrue(second.label.contains("Coffee") && second.label.contains("咖啡"), second.debugDescription)
    }

    @objc func testToolsPhotoQuotaKeepsLocallyRecognizedLinesOnIOS17() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-translation-relay-preview",
                               "--lio-translation-photo-quota-preview", "-cj.ui.language.v1", "en",
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
        let recognized = app.staticTexts["lio.translation.image-text"]
        XCTAssertTrue(recognized.waitForExistence(timeout: 12), app.debugDescription)
        XCTAssertEqual(recognized.label, "Tea\nCoffee")
        let notice = app.staticTexts["lio.translation.problem"]
        XCTAssertTrue(notice.waitForExistence(timeout: 6))
        XCTAssertTrue(notice.label.contains("iOS 18"))
        XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "lio.translation.line.0").firstMatch.exists)
    }

    @objc func testToolsAlreadyAcceptedTextDoesNotOfferAnotherSubmission() {
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
        editor.typeText("Already sent")
        let translate = app.buttons["lio.translation.submit"]
        translate.tap()
        let notice = app.staticTexts["lio.translation.problem"]
        XCTAssertTrue(notice.waitForExistence(timeout: 6))
        XCTAssertEqual(notice.label, "This translation was already sent.")
        XCTAssertFalse(translate.isEnabled)
        editor.tap()
        editor.typeText(" again")
        XCTAssertTrue(translate.isEnabled)
    }

    @objc func testToolsRelayFixtureReturnsTextOnIOS17() throws {
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
        app.buttons["lio.translation.submit"].tap()
        let result = app.staticTexts["lio.translation.result"]
        XCTAssertTrue(result.waitForExistence(timeout: 6))
        XCTAssertEqual(result.label, "你好")
        XCTAssertFalse(app.staticTexts["Offline translation"].exists)
    }
}
