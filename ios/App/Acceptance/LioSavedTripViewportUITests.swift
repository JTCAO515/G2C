import XCTest

@MainActor final class LioSavedTripViewportUITests: XCTestCase {
    func testEnglishListAndChatReturn() throws { try exercise(chinese: false) }
    func testChineseListAndChatReturn() throws { try exercise(chinese: true) }
    func testEnglishReducedMotionReturn() throws { try exerciseReducedMotion(chinese: false) }
    func testChineseReducedMotionReturn() throws { try exerciseReducedMotion(chinese: true) }

    private func exerciseReducedMotion(chinese: Bool) throws {
        let original = setSimulatorReduceMotion(true)
        defer { _ = setSimulatorReduceMotion(original) }
        try exercise(chinese: chinese)
    }

    // Same native Settings path as the existing Home acceptance suite.
    private func setSimulatorReduceMotion(_ enabled: Bool) -> Bool {
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        settings.launch()
        let accessibility = settings.cells["Accessibility"]
        for _ in 0..<8 {
            if accessibility.exists && accessibility.isHittable { break }
            settings.swipeUp()
        }
        XCTAssertTrue(accessibility.isHittable, settings.debugDescription)
        accessibility.tap()
        let motion = settings.cells["Motion"]
        XCTAssertTrue(motion.waitForExistence(timeout: 8), settings.debugDescription)
        motion.tap()
        let reduceMotion = settings.switches["Reduce Motion"]
        XCTAssertTrue(reduceMotion.waitForExistence(timeout: 8), settings.debugDescription)
        let original = reduceMotion.value as! String
        XCTAssertTrue(["0", "1"].contains(original))
        if (original == "1") != enabled { reduceMotion.tap() }
        XCTAssertEqual(reduceMotion.value as? String, enabled ? "1" : "0")
        settings.terminate()
        return original == "1"
    }

    func testEnglishDarkReturn() throws { try exercise(chinese: false, dark: true) }
    func testChineseDarkReturn() throws { try exercise(chinese: true, dark: true) }

    private func exercise(chinese: Bool, dark: Bool = false) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.viewport.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                               "-lio.ui.appearance.v1", dark ? "dark" : "light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch()
        defer { app.terminate() }
        let trips = app.tabBars.buttons[chinese ? "行程" : "Trips"]
        XCTAssertTrue(trips.waitForExistence(timeout: 12))
        trips.tap()
        let card = app.buttons["Draft"]
        XCTAssertTrue(card.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertTrue(card.isHittable)
        capture(app, "list-before")
        try audit(app)
        // Reopen the same source twice: an invisible source can still exist in AX.
        // Preserve screenshots for visual comparison as well as the touch/read checks.
        for visit in 1...2 {
            card.tap()
            let schedule = app.staticTexts[chinese ? "日期待定" : "Date to be decided"]
            XCTAssertTrue(schedule.waitForExistence(timeout: 8), app.debugDescription)
            XCTAssertTrue(app.staticTexts["Draft"].exists)
            capture(app, "detail-\(visit)")
            try audit(app)
            let viewports = app.scrollViews.containing(.staticText, identifier: "Draft")
            XCTAssertEqual(viewports.count, 1)
            let viewport = viewports.firstMatch
            XCTAssertTrue(viewport.exists)
            let geometry = XCTAttachment(string: viewport.debugDescription + "\n" + app.debugDescription)
            geometry.name = "actual-detail-viewport"; geometry.lifetime = .keepAlways; add(geometry)
            XCTAssertGreaterThan(viewport.frame.height, 0)
            XCTAssertGreaterThanOrEqual(viewport.frame.minY, app.navigationBars.firstMatch.frame.maxY)
            XCTAssertLessThanOrEqual(viewport.frame.maxY, app.tabBars.firstMatch.frame.minY)
            XCTAssertTrue(app.tabBars.firstMatch.exists, "Existing direct tab navigation remains available in detail")
            if visit == 1 {
                // The actual recorded structured.2 fixture contains all five entries.
                // Reaching each one rules out clipping or omitting data as an audit fix.
                // Keep each original entry clear of the bottom system gesture area.
                // 44pt is a deliberate reading margin, not an inferred device safe inset.
                let readableBottom = min(app.tabBars.firstMatch.frame.minY, app.windows.firstMatch.frame.maxY - 44)
                for label in ["我还没有决定出行日期 / Dates not decided", "合成公园", "123.50 m", "60 s", "Check opening hours"] {
                    let item = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label)).firstMatch
                    for _ in 0..<8 {
                        if item.exists && item.isHittable && item.frame.minY >= app.navigationBars.firstMatch.frame.maxY
                            && item.frame.maxY <= readableBottom { break }
                        if item.exists && item.frame.minY < app.navigationBars.firstMatch.frame.maxY {
                            app.swipeDown()
                        } else { app.swipeUp() }
                    }
                    XCTAssertTrue(item.exists && item.isHittable, "Unreachable original entry: \(label)")
                    XCTAssertGreaterThanOrEqual(item.frame.minY, app.navigationBars.firstMatch.frame.maxY)
                    XCTAssertLessThanOrEqual(item.frame.maxY, readableBottom)
                }
                capture(app, "all-original-entries-reached")
                try audit(app)
            }
            let back = app.navigationBars.buttons.firstMatch
            XCTAssertTrue(back.isHittable)
            back.tap()
            XCTAssertTrue(card.waitForExistence(timeout: 8))
            XCTAssertTrue(card.isHittable)
            XCTAssertFalse(schedule.exists)
            XCTAssertTrue(app.tabBars.firstMatch.exists)
            capture(app, "list-return-\(visit)")
        }
        try audit(app)
        app.tabBars.buttons[chinese ? "聊天" : "Chat"].tap()
        let show = app.buttons["lio.trip.show"]
        XCTAssertTrue(show.waitForExistence(timeout: 8))
        if !show.isHittable { app.swipeUp() }
        XCTAssertTrue(show.isHittable)
        capture(app, "chat-before")
        show.tap()
        let schedule = app.staticTexts[chinese ? "日期待定" : "Date to be decided"]
        XCTAssertTrue(schedule.waitForExistence(timeout: 8), app.debugDescription)
        capture(app, "chat-to-detail")
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(card.waitForExistence(timeout: 8))
        XCTAssertTrue(card.isHittable)
        app.tabBars.buttons[chinese ? "聊天" : "Chat"].tap()
        XCTAssertTrue(show.waitForExistence(timeout: 8))
        XCTAssertTrue(show.isHittable)
        capture(app, "chat-return")
        try audit(app)
    }

    private func audit(_ app: XCUIApplication) throws {
        let start = XCTAttachment(string: "audit-start-uptime=" + String(ProcessInfo.processInfo.systemUptime))
        start.name = "audit-interval-start"; start.lifetime = .keepAlways; add(start)
        defer {
            let end = XCTAttachment(string: "audit-end-uptime=" + String(ProcessInfo.processInfo.systemUptime))
            end.name = "audit-interval-end"; end.lifetime = .keepAlways; add(end)
        }
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No element") + "\n" + app.debugDescription)
            detail.name = "full-all-issue"; detail.lifetime = .keepAlways; self.add(detail)
            return false
        }
    }

    private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
