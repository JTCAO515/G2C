import XCTest

/// #2004 Stay: only collected hotels, filtered by price band; "Add to trip" gives a notice.
@MainActor extension LioToolsUITests {
    @objc func testStayListsCollectedHotelsAndFiltersByPrice() throws {
        continueAfterFailure = false
        func capture(_ app: XCUIApplication, _ name: String) {
            let screenshot = XCTAttachment(screenshot: app.screenshot())
            screenshot.name = name
            screenshot.lifetime = .keepAlways
            add(screenshot)
        }
        for (language, appearance) in [("en", "light"), ("zh-Hans", "dark")] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-place-tools-acceptance", "-cj.ui.language.v1", language,
                                   "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                   "UICTContentSizeCategoryL"]
            app.launch()
            defer { app.terminate() }
            XCTAssertTrue(app.descendants(matching: .any)["lio.places.development-banner"].waitForExistence(timeout: 8))
            func count() -> Int {
                app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'lio.stay.open.'")).count
            }
            XCTAssertEqual(count(), 4)
            capture(app, "stay-all-\(language)-\(appearance)")
            app.buttons["lio.stay.band.500-1000"].tap()
            XCTAssertEqual(count(), 1)
            XCTAssertTrue(app.buttons["lio.stay.open.pl_bj_b"].exists)
            app.buttons["lio.stay.city.shanghai"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["lio.stay.empty"].waitForExistence(timeout: 4))
            capture(app, "stay-empty-\(language)-\(appearance)")
            app.buttons["lio.stay.reset"].tap()
            XCTAssertEqual(count(), 4)
            app.buttons["lio.stay.add.pl_bj_a"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["lio.place.added"].waitForExistence(timeout: 4))
            capture(app, "stay-added-\(language)-\(appearance)")
        }
    }
}
