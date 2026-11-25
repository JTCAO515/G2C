import XCTest

@MainActor final class LioBuildUpdatesUITests: XCTestCase {
    private let currentBuild = "__UPDATES_CURRENT_BUILD__"
    private let previousBuild = "__UPDATES_PREVIOUS_BUILD__"
    private let olderBuild = "__UPDATES_OLDER_BUILD__"
    func testInvitationKeyboardTraits() throws {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.updates.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-onboarding-preview", "--lio-invitation-traits-acceptance"]
        app.launch()
        defer { app.terminate() }
        let traits = app.staticTexts["fixture.invitation.traits"]
        XCTAssertTrue(traits.waitForExistence(timeout: 8))
        let literal = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'literal-secure'"), object: traits)
        XCTAssertEqual(XCTWaiter.wait(for: [literal], timeout: 4), .completed)
    }

    func testInvitationDoneDismissesKeyboardWithoutContinuing() {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.updates.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-onboarding-preview", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        let field = app.secureTextFields["demo.invite.code"]
        XCTAssertTrue(field.waitForExistence(timeout: 8))
        field.tap()
        field.typeText("keyboard-check")
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.exists)
        app.navigationBars.buttons["lio.invite.keyboard-done"].tap()
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: keyboard)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
        XCTAssertTrue(app.buttons["demo.invite.continue"].isEnabled)
        XCTAssertFalse(app.buttons["demo.invite.signin"].exists)
    }

    func testInvitationEmptyDarkPageAccessibility() throws {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.updates.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-onboarding-preview", "-lio.ui.appearance.v1", "dark", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch()
        defer { app.terminate() }
        XCTAssertTrue(app.secureTextFields["demo.invite.code"].waitForExistence(timeout: 8))
        try audit(app)
    }

    func testInvitationFormatEnglish() throws { try exerciseInvitationFormat(chinese: false) }
    func testInvitationFormatChinese() throws { try exerciseInvitationFormat(chinese: true) }
    func testInvitationFormatLargestEnglish() throws { try exerciseInvitationFormat(chinese: false, largest: true) }
    func testInvitationFormatLargestChinese() throws { try exerciseInvitationFormat(chinese: true, largest: true) }

    private func revealInvitation(_ element: XCUIElement, app: XCUIApplication, towardTop: Bool) {
        let form = app.collectionViews.firstMatch
        let top = app.navigationBars.allElementsBoundByIndex.map { $0.frame.maxY }.max() ?? form.frame.minY
        let viewport = CGRect(x: form.frame.minX, y: max(top, form.frame.minY), width: form.frame.width,
                              height: form.frame.maxY - max(top, form.frame.minY))
        for _ in 0..<15 {
            if element.exists && element.isHittable && viewport.contains(element.frame) { return }
            if element.exists && !element.frame.isEmpty {
                let target = element.frame
                let delta = target.minY < viewport.minY
                    ? min(viewport.height * 0.4, max(30, viewport.minY - target.minY + 12))
                    : -min(viewport.height * 0.4, max(30, target.maxY - viewport.maxY + 12))
                let start = form.coordinate(withNormalizedOffset: CGVector(dx: 0.02, dy: 0.5))
                start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 0, dy: delta)), withVelocity: .slow, thenHoldForDuration: 0.2)
            } else if towardTop { form.swipeDown() } else { form.swipeUp() }
        }
        XCTAssertTrue(element.isHittable, app.debugDescription)
        XCTAssertTrue(viewport.contains(element.frame), app.debugDescription)
    }

    private func exerciseInvitationFormat(chinese: Bool, largest: Bool = false) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.updates.acceptance")
        for appearance in ["light", "dark"] {
            app.launchArguments = ["--lio-preview", "--lio-onboarding-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                largest ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
            app.launch()
            let field = app.secureTextFields["demo.invite.code"]
            XCTAssertTrue(field.waitForExistence(timeout: 12))
            let malformed = "g2c@1 "
            field.tap(); field.typeText(malformed)
            app.buttons["demo.invite.continue"].tap()
            let format = app.staticTexts["demo.invite.format"]
            revealInvitation(format, app: app, towardTop: false)
            XCTAssertTrue(format.label.contains("G2C@"))
            XCTAssertTrue(format.label.contains("CJ_Tester@"))
            XCTAssertFalse(app.staticTexts["demo.invite.consent"].exists)
            XCTAssertFalse(app.staticTexts[malformed].exists)
            try audit(app)
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "invitation-format-\(chinese ? "zh" : "en")-\(appearance)-\(largest ? "largest" : "normal")"
            shot.lifetime = .keepAlways; add(shot)
            revealInvitation(field, app: app, towardTop: true)
            field.tap(); field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: malformed.count))
            field.typeText(chinese ? "CJ_Tester@01" : "G2C@01")
            app.buttons["demo.invite.continue"].tap()
            XCTAssertTrue(app.staticTexts["demo.invite.consent"].waitForExistence(timeout: 5))
            try audit(app)
            app.terminate()
        }
    }

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
            openInformation(app, chinese: chinese)
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
        openInformation(app, chinese: chinese)
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
            app.launchArguments += ["-UIPreferredContentSizeCategoryName", largest ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
            app.launch()
            defer { app.terminate() }
            let code = app.secureTextFields["demo.invite.code"]
            XCTAssertTrue(code.waitForExistence(timeout: 12))
            XCTAssertFalse(app.buttons["demo.invite.continue"].isEnabled)
            code.tap(); code.typeText("D1-aaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbb")
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
            openInformation(app, chinese: chinese)
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
            // Closing the information page returns to the Me tab's row (#1452).
            XCTAssertTrue(app.buttons["lio.information"].waitForExistence(timeout: 5))
            app.terminate()
        }
    }

    /// #1452: the information page moved from the chat menu to the Me tab's settings and account rows.
    private func openInformation(_ app: XCUIApplication, chinese: Bool) {
        let me = app.tabBars.buttons[chinese ? "我的" : "Me"]
        XCTAssertTrue(me.waitForExistence(timeout: 12))
        me.tap()
        let info = app.buttons["lio.information"]
        // Large text can leave this row outside the lazy list's current elements.
        for _ in 0..<8 {
            if info.exists && info.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(info.isHittable, info.debugDescription)
        info.tap()
    }

    private func reveal(_ element: XCUIElement, app: XCUIApplication) {
        let scroll = app.scrollViews["lio.information.scroll"]
        guard let navigationBottom = app.navigationBars.allElementsBoundByIndex.map({ $0.frame.maxY }).max() else {
            XCTFail("Expected the existing information navigation bar", file: #filePath, line: #line)
            return
        }
        let bounds = scroll.frame
        let done = app.buttons["lio.information.done"]
        let controlsBottom = done.exists ? done.frame.maxY + 8 : navigationBottom
        let top = max(bounds.minY, navigationBottom, controlsBottom)
        let viewport = CGRect(x: bounds.minX, y: top, width: bounds.width, height: bounds.maxY - top)
        XCTAssertGreaterThan(viewport.height, 0)
        let step = viewport.height * 0.35
        let start = app.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: viewport.minX + 8, dy: viewport.midY))
        var returnedToHeading = false
        var covered: CGFloat = 0
        var paragraphSize: CGSize?
        var previous: CGRect?
        var unchanged = 0
        for _ in 0..<80 {
            let exists = element.exists
            let frame = exists ? element.frame : .zero
            if !exists || frame.isEmpty {
                if !returnedToHeading {
                    let heading = app.staticTexts["lio.updates.heading"]
                    for _ in 0..<30 {
                        if heading.exists && viewport.contains(heading.frame) { break }
                        scroll.swipeDown(velocity: .fast)
                    }
                    XCTAssertTrue(heading.exists && viewport.contains(heading.frame), app.debugDescription)
                    returnedToHeading = true
                } else {
                    start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 0, dy: -step)), withVelocity: .slow, thenHoldForDuration: 0.2)
                }
                continue
            }
            unchanged = previous == frame ? unchanged + 1 : 0
            previous = frame
            guard unchanged < 3 else {
                XCTFail("The actual element did not advance: \(element.identifier), frame \(frame), viewport \(viewport), covered \(covered)")
                return
            }
            let delta: CGFloat
            if frame.height > viewport.height {
                if let size = paragraphSize,
                   abs(size.height - frame.height) > 1 || abs(size.width - frame.width) > 1 {
                    // Reflow invalidates pixel offsets; re-read the new layout
                    // from its beginning instead of crediting old coverage.
                    covered = 0
                }
                paragraphSize = frame.size
                let first = max(0, viewport.minY - frame.minY)
                let last = min(frame.height, viewport.maxY - frame.minY)
                // Every readable slice must overlap the already covered text;
                // a skipped middle cannot be treated as a complete paragraph.
                if last > first && first <= covered + 1 { covered = max(covered, last) }
                if covered >= frame.height - 1 {
                    XCTAssertTrue(element.isHittable)
                    XCTAssertGreaterThanOrEqual(covered, frame.height - 1)
                    return
                }
                let wantedOffset = max(0, covered - 24)
                delta = min(step, max(-step, viewport.minY - frame.minY - wantedOffset))
            } else {
                if viewport.contains(frame) {
                    var lastFrame: CGRect?
                    let stable = NSPredicate { _, _ in
                        guard element.exists, element.isHittable, viewport.contains(element.frame) else { return false }
                        let current = element.frame
                        defer { lastFrame = current }
                        return lastFrame == current
                    }
                    XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: stable, object: nil)], timeout: 5), .completed)
                    XCTAssertTrue(element.isHittable)
                    XCTAssertTrue(viewport.contains(element.frame))
                    return
                }
                delta = min(step, max(-step, viewport.midY - frame.midY))
            }
            // Tiny drags fall below UIKit’s scroll threshold. Keep the gesture
            // observable; the next snapshot must still prove full coverage.
            let gestureDelta = delta >= 0 ? max(35, delta) : min(-35, delta)
            start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 0, dy: gestureDelta)), withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        XCTFail("The complete paragraph was not read within the bounded scroll sequence")
    }
    private func audit(_ app: XCUIApplication) throws {
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: issue.compactDescription + "\n" + issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No audit element") + "\n" + app.debugDescription)
            detail.name = "updates-audit"; detail.lifetime = .keepAlways; self.add(detail)
            return false
        }
    }
}
