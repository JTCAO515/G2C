import XCTest

@MainActor final class LioExitCapsuleUITests: XCTestCase {
    func testEnglishOptionsSendOnceAndDisappear() throws { try exercise(chinese: false, dark: false, largest: false) }
    func testChineseOptionsSendOnceAndDisappear() throws { try exercise(chinese: true, dark: false, largest: false) }
    func testEnglishLargestDarkOptionsRemainReadable() throws { try exercise(chinese: false, dark: true, largest: true) }
    func testChineseLargestDarkOptionsRemainReadable() throws { try exercise(chinese: true, dark: true, largest: true) }

    func testMissingAndDisabledOptionsNeverSend() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.exits.acceptance")
        for chinese in [false, true] {
            for flag in ["--empty-exits", "--disabled-exits"] {
                app.launchArguments = ["--lio-preview", flag, "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
                app.launch()
                let count = app.staticTexts["fixture.exit.count"]
                XCTAssertTrue(count.waitForExistence(timeout: 10))
                let plan = app.buttons["lio.exit.plan_now"]
                if flag == "--empty-exits" { XCTAssertFalse(plan.exists) }
                else { XCTAssertTrue(plan.exists); XCTAssertFalse(plan.isEnabled) }
                XCTAssertEqual(count.label, "0")
                try app.performAccessibilityAudit(for: .all)
                app.terminate()
            }
        }
    }

    func testThreeOptionsSendTheChosenExactText() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.exits.acceptance")
        for chinese in [false, true] {
            app.launchArguments = ["--lio-preview", "--three-exits", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                "-lio.ui.appearance.v1", chinese ? "light" : "dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
            app.launch()
            let adjust = app.buttons["lio.exit.adjust"]
            XCTAssertTrue(adjust.waitForExistence(timeout: 10))
            XCTAssertTrue(adjust.isHittable)
            XCTAssertGreaterThanOrEqual(adjust.frame.height, 44)
            try app.performAccessibilityAudit(for: .all)
            adjust.tap()
            XCTAssertEqual(app.staticTexts["fixture.exit.count"].label, "1")
            XCTAssertEqual(app.staticTexts["fixture.exit.sent"].label,
                chinese ? "请帮我换一个旅行方向" : "Please change the travel direction")
            for id in ["plan_now", "explore", "adjust"] { XCTAssertFalse(app.buttons["lio.exit." + id].exists) }
            app.terminate()
        }
    }

    private func exercise(chinese: Bool, dark: Bool, largest: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.exits.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
            "-lio.ui.appearance.v1", dark ? "dark" : "light", "-UIPreferredContentSizeCategoryName",
            largest ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
        app.launch()
        defer { app.terminate() }
        let plan = app.buttons["lio.exit.plan_now"]
        let explore = app.buttons["lio.exit.explore"]
        XCTAssertTrue(plan.waitForExistence(timeout: 10))
        XCTAssertEqual(plan.label, chinese ? "先排行程" : "Plan now")
        XCTAssertEqual(explore.label, chinese ? "再看看方向" : "Explore more")
        XCTAssertTrue(plan.isHittable)
        XCTAssertTrue(explore.isHittable)
        for button in [plan, explore] {
            XCTAssertGreaterThanOrEqual(button.frame.height, 44)
            XCTAssertTrue(app.frame.contains(button.frame))
        }
        try app.performAccessibilityAudit(for: .all)
        let options = XCTAttachment(screenshot: app.screenshot())
        options.name = "exit-capsules-\(chinese ? "zh" : "en")-\(dark ? "dark" : "light")"
        options.lifetime = .keepAlways; add(options)
        plan.tap()
        XCTAssertEqual(app.staticTexts["fixture.exit.count"].label, "1")
        XCTAssertEqual(app.staticTexts["fixture.exit.sent"].label,
            chinese ? "请先帮我安排三天行程" : "Please make a three-day plan")
        XCTAssertFalse(plan.exists, "Consumed options must disappear after the one send")
        XCTAssertFalse(explore.exists)
        try app.performAccessibilityAudit(for: .all)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "consumed-exits-\(chinese ? "zh" : "en")-\(dark ? "dark" : "light")"
        shot.lifetime = .keepAlways; add(shot)
    }
}
