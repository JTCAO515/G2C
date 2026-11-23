import XCTest

@MainActor extension LioToolsUITests {
    @objc func testNearbyFixtureUsesManualSearchAndOffersFiveActions() {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-nearby-preview",
                               "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.nearby"].tap()
        app.buttons["Use my location"].tap()
        XCTAssertTrue(app.staticTexts["Location is unavailable. Enter a place to continue."].exists)

        let search = app.textFields["Enter a place"]
        search.tap()
        search.typeText("Beijing")
        app.buttons["Search"].tap()
        let place = app.buttons.containing(NSPredicate(format: "label CONTAINS %@", "川味小馆")).firstMatch
        XCTAssertTrue(place.waitForExistence(timeout: 6))
        place.tap()
        for title in ["Taxi here", "Directions", "Show the address", "Ask Lio", "Add to trip"] {
            XCTAssertTrue(app.buttons[title].exists)
        }
        app.buttons["Taxi here"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Sichuan Kitchen")).firstMatch.waitForExistence(timeout: 6))
    }
}
