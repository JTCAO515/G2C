import XCTest

@MainActor extension LioToolsUITests {
    @objc func testCurrencyFixtureConvertsInBothDirectionsAndShowsRateDate() throws {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-currency-preview",
                               "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        let currency = app.buttons["lio.tools.currency"]
        XCTAssertTrue(currency.waitForExistence(timeout: 6))
        currency.tap()

        let result = app.staticTexts["lio.currency.result"]
        XCTAssertTrue(result.waitForExistence(timeout: 6))
        XCTAssertEqual(result.label, "15.63 USD")
        XCTAssertTrue(app.staticTexts["lio.currency.source"].label.contains("ECB · 2026-11-20"))
        try app.performAccessibilityAudit(for: .all)

        app.buttons["lio.currency.swap"].tap()
        XCTAssertEqual(result.label, "640.00 CNY")
    }
}
