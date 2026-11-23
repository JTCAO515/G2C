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
        XCTAssertFalse(app.staticTexts["Embassy of the Republic of Korea"].exists)
        app.terminate()
        app.launch()
        openLocalSupport(app)
        showNationalityButton(in: app)
        XCTAssertTrue(app.staticTexts["Embassy of Japan"].exists)
        XCTAssertFalse(app.staticTexts["Embassy of the Republic of Korea"].exists)
    }

    private func openLocalSupport(_ app: XCUIApplication) {
        let tools = app.tabBars.buttons["Tools"]
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
}
