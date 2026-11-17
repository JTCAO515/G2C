import XCTest

@MainActor final class LioTripEmptyUITests: XCTestCase {
    func testEnglishLightEmptyTripAction() throws { try exercise(chinese: false, appearance: "light") }
    func testChineseLightEmptyTripAction() throws { try exercise(chinese: true, appearance: "light") }
    func testEnglishDarkEmptyTripAction() throws { try exercise(chinese: false, appearance: "dark") }
    func testChineseDarkEmptyTripAction() throws { try exercise(chinese: true, appearance: "dark") }

    private func exercise(chinese: Bool, appearance: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.trip.empty.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                               "-lio.ui.appearance.v1", appearance,
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch()
        defer { app.terminate() }
        let chat = app.tabBars.buttons[chinese ? "聊天" : "Chat"]
        let trips = app.tabBars.buttons[chinese ? "行程" : "Trips"]
        XCTAssertTrue(trips.waitForExistence(timeout: 12))
        trips.tap()
        XCTAssertTrue(trips.isSelected)
        let action = app.buttons[chinese ? "和 Lio 聊聊" : "Chat with Lio"]
        XCTAssertTrue(action.waitForExistence(timeout: 8))
        XCTAssertTrue(action.isHittable)
        XCTAssertTrue(app.staticTexts[chinese ? "还没有行程" : "No trips yet"].exists)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "empty-trip-\(chinese ? "zh" : "en")-\(appearance)"; shot.lifetime = .keepAlways; add(shot)
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No element") + "\n" + app.debugDescription)
            detail.name = "empty-trip-complete-all"; detail.lifetime = .keepAlways; self.add(detail)
            return false
        }
        action.tap()
        XCTAssertTrue(chat.isSelected)
        XCTAssertFalse(trips.isSelected)
        XCTAssertTrue(app.staticTexts["lio.opening"].waitForExistence(timeout: 8))
    }
}
