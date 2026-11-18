import XCTest

@MainActor final class LioFailureNextStepUITests: XCTestCase {
    func testAcceptedFailureOffersNotesWithoutSendingAgain() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.failure-help.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", "__FAILURE_SCENARIO__",
                               "-cj.ui.language.v1", "__FAILURE_LANGUAGE__", "-lio.ui.appearance.v1", "__FAILURE_APPEARANCE__"]
        app.launch()
        defer { app.terminate() }
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(composer.waitForExistence(timeout: 15))
        composer.tap(); composer.typeText("Plan a short trip.")
        app.buttons["lio.send"].tap()
        let failure = app.staticTexts["lio.failure"]
        XCTAssertTrue(failure.waitForExistence(timeout: 10))
        XCTAssertEqual(failure.label, "__FAILURE_TEXT__")
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")
        XCTAssertFalse(app.staticTexts["lio.answer"].exists)
        XCTAssertFalse(app.buttons["lio.source"].exists)
        XCTAssertFalse(app.staticTexts["Amap Weather"].exists)
        XCTAssertFalse(app.buttons["lio.resend"].exists)
        XCTAssertFalse(app.buttons["lio.askAgain"].exists)
        let before = XCTAttachment(screenshot: app.screenshot())
        before.name = "accepted-failure-before-help"; before.lifetime = .keepAlways; add(before)
        let help = app.buttons["lio.failure.problems"]
        XCTAssertTrue(help.waitForExistence(timeout: 8))
        XCTAssertGreaterThanOrEqual(help.frame.height, 44)
        XCTAssertTrue(app.staticTexts["lio.failure.next-step"].exists)
        try app.performAccessibilityAudit(for: .all)
        help.tap()
        XCTAssertTrue(app.staticTexts["lio.problems.heading"].waitForExistence(timeout: 8))
        let records = app.descendants(matching: .any).matching(identifier: "lio.problems.list").firstMatch
        XCTAssertTrue(records.waitForExistence(timeout: 8))
        XCTAssertEqual(records.value as? String, "__EMPTY_NOTES_TEXT__")
        XCTAssertFalse(app.buttons["lio.problems.copy"].exists)
        try app.performAccessibilityAudit(for: .all)
        let notes = XCTAttachment(screenshot: app.screenshot())
        notes.name = "existing-problem-notes"; notes.lifetime = .keepAlways; add(notes)
        app.buttons["lio.problems.done"].tap()
        XCTAssertTrue(failure.waitForExistence(timeout: 8))
        XCTAssertEqual(failure.label, "__FAILURE_TEXT__")
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")
        XCTAssertFalse(app.buttons["lio.resend"].exists)
        XCTAssertFalse(app.buttons["lio.askAgain"].exists)
    }
}
