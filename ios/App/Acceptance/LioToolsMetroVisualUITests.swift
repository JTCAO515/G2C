import XCTest

@MainActor extension LioToolsUITests {
    /// #2008: a big city's map opens on its centre (stations legible), "Whole map" and "City centre" switch, a small
    /// city opens whole; the paper, water and official line colours are the new look.
    @objc func testMetroMapOpensOnTheCityCentre() throws {
        continueAfterFailure = false
        func capture(_ app: XCUIApplication, _ name: String) {
            let screenshot = XCTAttachment(screenshot: app.screenshot())
            screenshot.name = name
            screenshot.lifetime = .keepAlways
            add(screenshot)
        }
        for (language, appearance, cities) in [("en", "light", ["beijing", "shanghai", "guangzhou", "lanzhou"]),
                                               ("zh-Hans", "dark", ["shanghai", "chongqing"])] {
            let english = language == "en"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                   "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                   "UICTContentSizeCategoryL"]
            app.launch()
            defer { app.terminate() }
            let tools = app.tabBars.buttons[english ? "Tools" : "工具"]
            XCTAssertTrue(tools.waitForExistence(timeout: 8))
            tools.tap()
            app.buttons["lio.tools.metro-guide"].tap()
            for city in cities {
                let card = app.buttons["lio.metro.city.\(city)"]
                var swipes = 0
                while !card.isHittable && swipes < 12 { app.swipeUp(); swipes += 1 }
                XCTAssertTrue(card.waitForExistence(timeout: 6), city)
                card.tap()
                XCTAssertTrue(app.descendants(matching: .any)["lio.metro.map.canvas"].waitForExistence(timeout: 8))
                let centre = app.buttons["lio.metro.map.center"]
                if city == "lanzhou" {
                    XCTAssertFalse(centre.exists, "a small network opens whole and has no centre button")
                } else {
                    XCTAssertTrue(centre.exists, city)
                    XCTAssertFalse(centre.isEnabled, "\(city) opens on its centre")
                    capture(app, "metro-centre-\(city)-\(language)-\(appearance)")
                    app.buttons["lio.metro.map.fit"].tap()
                    XCTAssertTrue(centre.isEnabled)
                    capture(app, "metro-whole-\(city)-\(language)-\(appearance)")
                    centre.tap()
                    XCTAssertFalse(centre.isEnabled)
                }
                if city == "lanzhou" { capture(app, "metro-whole-lanzhou-\(language)-\(appearance)") }
                app.navigationBars.buttons.element(boundBy: 0).tap()
            }
        }
    }
}
