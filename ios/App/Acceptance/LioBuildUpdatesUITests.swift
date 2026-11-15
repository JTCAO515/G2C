import XCTest

@MainActor final class LioBuildUpdatesUITests: XCTestCase {
    private let currentBuild = "__UPDATES_CURRENT_BUILD__"
    private let previousBuild = "__UPDATES_PREVIOUS_BUILD__"
    private let olderBuild = "__UPDATES_OLDER_BUILD__"
    func testEnglish() throws { try exercise(chinese: false, largest: false) }
    func testChinese() throws { try exercise(chinese: true, largest: false) }
    func testEnglishLargest() throws { try exercise(chinese: false, largest: true) }
    func testChineseLargest() throws { try exercise(chinese: true, largest: true) }
    func testEnglishLargestLight() throws { try exercise(chinese: false, largest: true, appearances: ["light"]) }
    func testEnglishLargestDark() throws { try exercise(chinese: false, largest: true, appearances: ["dark"]) }
    func testChineseLargestLight() throws { try exercise(chinese: true, largest: true, appearances: ["light"]) }
    func testChineseLargestDark() throws { try exercise(chinese: true, largest: true, appearances: ["dark"]) }

    func testLargestDarkScrollContrastInBothLanguages() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.updates.acceptance")
        for chinese in [false, true] {
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                "-lio.ui.appearance.v1", "dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
            app.launch()
            defer { app.terminate() }
            XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
            app.buttons["lio.menu"].tap()
            XCTAssertTrue(app.buttons["lio.information"].waitForExistence(timeout: 5))
            app.buttons["lio.information"].tap()
            for identifier in ["lio.updates.\(currentBuild).comparison.0", "lio.updates.\(currentBuild).service.0",
                               "lio.updates.\(previousBuild).changes.0"] {
                reveal(app.textViews[identifier], app: app)
                try audit(app)
            }
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "updates-deep-scroll-\(chinese ? "zh" : "en")-dark-largest"
            shot.lifetime = .keepAlways; add(shot)
            app.terminate()
        }
    }

    func testLargestChinesePreviousServiceDirect() throws {
        try exerciseDirectSection(chinese: true, appearance: "light", build: previousBuild, section: "service")
    }
    func testLargestDirectSection() throws {
        let env = ProcessInfo.processInfo.environment
        if env["LIO_UPDATES_TEST_LANGUAGE"] == nil && env["LIO_UPDATES_TEST_APPEARANCE"] == nil
            && env["LIO_UPDATES_TEST_PERIOD"] == nil && env["LIO_UPDATES_TEST_SECTION"] == nil {
            try exerciseDirectSection(chinese: false, appearance: "dark", build: currentBuild, section: "changes")
            return
        }
        guard let locale = env["LIO_UPDATES_TEST_LANGUAGE"], let appearance = env["LIO_UPDATES_TEST_APPEARANCE"],
              let period = env["LIO_UPDATES_TEST_PERIOD"], let section = env["LIO_UPDATES_TEST_SECTION"] else {
            XCTFail("Explicit section diagnostic parameters are required")
            return
        }
        XCTAssertTrue(["zh", "en"].contains(locale))
        XCTAssertTrue(["light", "dark"].contains(appearance))
        XCTAssertTrue(["current", "previous"].contains(period))
        XCTAssertTrue(["changes", "comparison", "testing", "known", "service"].contains(section))
        try exerciseDirectSection(chinese: locale == "zh", appearance: appearance,
                                  build: period == "current" ? currentBuild : previousBuild, section: section)
    }
    private func exerciseDirectSection(chinese: Bool, appearance: String, build: String, section: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.updates.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", appearance,
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        defer { app.terminate() }
        XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
        app.buttons["lio.menu"].tap()
        XCTAssertTrue(app.buttons["lio.information"].waitForExistence(timeout: 5))
        app.buttons["lio.information"].tap()
        let paragraph = app.textViews["lio.updates.\(build).\(section).0"]
        reveal(paragraph, app: app)
        XCTAssertFalse((paragraph.value as? String ?? "").isEmpty)
        try audit(app)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "updates-direct-\(chinese ? "zh" : "en")-\(appearance)-\(build)-\(section)"
        shot.lifetime = .keepAlways; add(shot)
        let done = app.buttons["lio.information.done"]
        XCTAssertTrue(done.isHittable)
        done.tap()
        XCTAssertTrue(app.buttons["lio.information"].waitForExistence(timeout: 5))
    }

    private func exercise(chinese: Bool, largest: Bool, appearances: [String] = ["light", "dark"]) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.updates.acceptance")
        for appearance in appearances {
            app.launchArguments = ["--lio-preview", "--lio-onboarding-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                   "-lio.ui.appearance.v1", appearance]
            if largest { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
            app.launch()
            defer { app.terminate() }
            let code = app.secureTextFields["demo.invite.code"]
            XCTAssertTrue(code.waitForExistence(timeout: 12))
            XCTAssertFalse(app.buttons["demo.invite.continue"].isEnabled)
            code.tap(); code.typeText("synthetic-only")
            app.buttons["demo.invite.continue"].tap()
            let consent = app.staticTexts["demo.invite.consent"]
            XCTAssertTrue(consent.waitForExistence(timeout: 5))
            XCTAssertEqual(consent.label, chinese ? "这是内部演示。请使用虚构的旅行信息，别填写个人信息。" : "This is an internal demo. Please use fictional trip details and leave out personal information.")
            try audit(app)
            reveal(app.buttons["lio.invite.back"], app: app)
            app.buttons["lio.invite.back"].tap()
            XCTAssertTrue(code.waitForExistence(timeout: 5))
            XCTAssertTrue(app.buttons["demo.invite.continue"].isEnabled)
            app.buttons["demo.invite.continue"].tap()
            let agree = app.buttons["demo.invite.signin"]
            reveal(agree, app: app)
            XCTAssertTrue(agree.isEnabled)
            agree.tap()
            let menu = app.buttons["lio.menu"]
            XCTAssertTrue(menu.waitForExistence(timeout: 10))
            menu.tap()
            let info = app.buttons["lio.information"]
            XCTAssertTrue(info.waitForExistence(timeout: 5))
            info.tap()
            XCTAssertTrue(consent.waitForExistence(timeout: 5))
            XCTAssertFalse(app.buttons["demo.invite.signin"].exists)
            let build = app.staticTexts["lio.updates.current-build"]
            reveal(build, app: app)
            XCTAssertEqual(build.label, chinese ? "当前构建：\(currentBuild)" : "Current build: \(currentBuild)")
            for section in ["changes", "comparison", "testing", "known", "service"] {
                let heading = app.staticTexts["lio.updates.\(currentBuild)." + section]
                reveal(heading, app: app)
                XCTAssertTrue(heading.exists)
                let paragraph = app.textViews["lio.updates.\(currentBuild)." + section + ".0"]
                reveal(paragraph, app: app)
                XCTAssertFalse((paragraph.value as? String ?? "").isEmpty)
                try audit(app)
                let image = XCTAttachment(screenshot: app.screenshot())
                image.name = "updates-\(chinese ? "zh" : "en")-\(appearance)-\(largest ? "largest" : "normal")-\(section)"
                image.lifetime = .keepAlways; add(image)
            }
            let previous = app.staticTexts["lio.updates.previous"]
            reveal(previous, app: app)
            XCTAssertEqual(previous.label, chinese ? "上一构建：\(previousBuild)" : "Previous build: \(previousBuild)")
            for section in ["changes", "comparison", "testing", "known", "service"] {
                reveal(app.textViews["lio.updates.\(previousBuild)." + section + ".0"], app: app)
                try audit(app)
            }
            XCTAssertFalse(app.staticTexts["lio.updates.\(olderBuild).changes"].exists)
            let done = app.buttons["lio.information.done"]
            XCTAssertTrue(done.isHittable)
            XCTAssertTrue(app.frame.contains(done.frame))
            XCTAssertGreaterThanOrEqual(done.frame.height, 44)
            done.tap()
            XCTAssertTrue(info.waitForExistence(timeout: 5))
            app.terminate()
        }
    }

    private func reveal(_ element: XCUIElement, app: XCUIApplication) {
        let scroll = app.scrollViews["lio.information.scroll"]
        guard let navigationBottom = app.navigationBars.allElementsBoundByIndex.map({ $0.frame.maxY }).max() else {
            XCTFail("Expected the existing information navigation bar", file: #filePath, line: #line)
            return
        }
        let bounds = scroll.frame
        let top = max(bounds.minY, navigationBottom)
        let viewport = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)
        XCTAssertGreaterThan(viewport.height, 0)
        var returnedToHeading = false
        for _ in 0..<80 {
            if !returnedToHeading && (!element.exists || element.frame.isEmpty) {
                let heading = app.staticTexts["lio.updates.heading"]
                for _ in 0..<30 {
                    if heading.exists && viewport.contains(heading.frame) { break }
                    scroll.swipeDown(velocity: .fast)
                }
                XCTAssertTrue(heading.exists && viewport.contains(heading.frame), app.debugDescription)
                returnedToHeading = true
            }
            if element.exists && !element.frame.isEmpty && viewport.contains(element.frame) {
                var lastFrame: CGRect?
                let stable = NSPredicate { _, _ in
                    guard element.exists, element.isHittable, viewport.contains(element.frame) else { return false }
                    let current = element.frame
                    defer { lastFrame = current }
                    return lastFrame == current
                }
                XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: stable, object: nil)], timeout: 5), .completed)
                return
            }
            let frame = viewport
            let target = element.exists && !element.frame.isEmpty ? element.frame : CGRect(x: frame.midX, y: frame.maxY + frame.height, width: 1, height: 1)
            let delta = target.minY < frame.minY ? min(frame.height * 0.4, max(80, frame.minY - target.minY + 12))
                : -min(frame.height * 0.4, max(80, target.maxY - frame.maxY + 12))
            let start = scroll.coordinate(withNormalizedOffset: CGVector(dx: 0.02, dy: 0.5))
            start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 0, dy: delta)))
        }
        XCTAssertTrue(element.isHittable, app.debugDescription)
        XCTAssertTrue(viewport.contains(element.frame), app.debugDescription)
    }
    private func audit(_ app: XCUIApplication) throws {
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: issue.compactDescription + "\n" + issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No audit element") + "\n" + app.debugDescription)
            detail.name = "updates-audit"; detail.lifetime = .keepAlways; self.add(detail)
            return false
        }
    }
}
