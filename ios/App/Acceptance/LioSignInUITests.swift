import XCTest

@MainActor final class LioSignInUITests: XCTestCase {
    /// #1891: "1" when the generated build turns on `G2CNewSignInScreenEnabled`.
    private let newScreen = "__SIGNIN_NEW_SCREEN__" == "1"

    /// Runs first (before anything is signed in): the new screens at the largest accessibility text size.
    func testA_NewSignInAtLargestTextSize() throws {
        try XCTSkipUnless(newScreen, "only for the new sign-in screen")
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["B691_LOCAL_ENDPOINT": "__SIGNIN_ENDPOINT__"]
        app.launchArguments = ["-cj.ui.language.v1", "__SIGNIN_LANGUAGE__", "-lio.ui.appearance.v1", "__SIGNIN_APPEARANCE__",
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.staticTexts["lio.signin.heading"].waitForExistence(timeout: 10))
        try app.performAccessibilityAudit(for: .all)
        keep(app, "welcome-ax5-__SIGNIN_LANGUAGE__-__SIGNIN_APPEARANCE__")
        let invite = app.buttons["lio.signin.invite"]
        for _ in 0..<6 where !invite.isHittable { app.swipeUp() }
        XCTAssertTrue(invite.isHittable)
        try app.performAccessibilityAudit(for: .all)
        keep(app, "welcome-ax5-end-__SIGNIN_LANGUAGE__-__SIGNIN_APPEARANCE__")
        invite.tap()
        XCTAssertTrue(app.secureTextFields["demo.invite.code"].waitForExistence(timeout: 10))
        try app.performAccessibilityAudit(for: .all)
        keep(app, "invite-ax5-__SIGNIN_LANGUAGE__-__SIGNIN_APPEARANCE__")
        let restore = app.buttons["demo.invite.restore"]
        for _ in 0..<6 where !restore.isHittable { app.swipeUp() }
        XCTAssertTrue(restore.isHittable)
        try app.performAccessibilityAudit(for: .all)
        app.terminate()
    }

    /// The new first screen: three placeholder channels that only explain they are coming soon, and two ways to the
    /// internal test page (from the notice and from the small entry). Ends on the internal test page.
    private func enterThroughNewScreen(_ app: XCUIApplication) throws {
        XCTAssertTrue(app.staticTexts["lio.signin.heading"].waitForExistence(timeout: 10))
        for id in ["lio.signin.apple", "lio.signin.google", "lio.signin.email", "lio.signin.invite"] {
            XCTAssertTrue(app.buttons[id].isHittable, id)
            XCTAssertGreaterThanOrEqual(app.buttons[id].frame.height, 44, id)
        }
        XCTAssertFalse(app.secureTextFields["demo.invite.code"].exists)
        try app.performAccessibilityAudit(for: .all)
        keep(app, "welcome-__SIGNIN_LANGUAGE__-__SIGNIN_APPEARANCE__")
        for (index, id) in ["lio.signin.apple", "lio.signin.google", "lio.signin.email"].enumerated() {
            app.buttons[id].tap()
            let alert = app.alerts.firstMatch
            XCTAssertTrue(alert.waitForExistence(timeout: 5), id)
            XCTAssertTrue(alert.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "__SIGNIN_SOON_TEXT__")).firstMatch.exists, id)
            if index == 0 { keep(app, "coming-soon-__SIGNIN_LANGUAGE__-__SIGNIN_APPEARANCE__") }
            if index < 2 {
                alert.buttons["__SIGNIN_OK__"].tap()
                XCTAssertTrue(alert.waitForNonExistence(timeout: 5), id)
                XCTAssertTrue(app.staticTexts["lio.signin.heading"].exists, id)
            } else {
                alert.buttons["lio.signin.soon.invite"].tap()
            }
        }
        XCTAssertTrue(app.secureTextFields["demo.invite.code"].waitForExistence(timeout: 10))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(app.buttons["lio.signin.invite"].waitForExistence(timeout: 10))
        app.buttons["lio.signin.invite"].tap()
        XCTAssertTrue(app.staticTexts["lio.invite.heading"].waitForExistence(timeout: 10))
    }

    private func keep(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testLioSignInWithoutLegacyStarterData() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["B691_LOCAL_ENDPOINT": "__SIGNIN_ENDPOINT__"]
        app.launchArguments = ["-cj.ui.language.v1", "__SIGNIN_LANGUAGE__",
                               "-lio.ui.appearance.v1", "__SIGNIN_APPEARANCE__"]
        app.launch()
        if newScreen { try enterThroughNewScreen(app) }
        let code = app.secureTextFields["demo.invite.code"]
        XCTAssertTrue(code.waitForExistence(timeout: 10))
        let next = app.buttons["demo.invite.continue"]
        let restore = app.buttons["demo.invite.restore"]
        XCTAssertFalse(next.isEnabled)
        XCTAssertTrue(restore.isEnabled)
        XCTAssertGreaterThanOrEqual(next.frame.height, 44)
        XCTAssertGreaterThanOrEqual(restore.frame.height, 44)
        try app.performAccessibilityAudit(for: .all)
        let empty = XCTAttachment(screenshot: app.screenshot())
        empty.name = "invitation-empty-__SIGNIN_LANGUAGE__-__SIGNIN_APPEARANCE__"
        empty.lifetime = .keepAlways; add(empty)
        code.tap(); code.typeText("D1-aaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbb")
        XCTAssertTrue(next.isEnabled)
        XCTAssertGreaterThanOrEqual(next.frame.height, 44)
        app.buttons["demo.invite.continue"].tap()
        let agree = app.buttons["demo.invite.signin"]
        XCTAssertTrue(agree.waitForExistence(timeout: 10))
        XCTAssertTrue(agree.isHittable); agree.tap()
        if "__SIGNIN_SCENARIO__" == "malformed" {
            let error = app.staticTexts["demo.invite.status"]
            XCTAssertTrue(error.waitForExistence(timeout: 20))
            XCTAssertTrue(error.label.contains("__SIGNIN_ERROR_TEXT__"))
            XCTAssertEqual(app.staticTexts["fixture.signin.state"].label, "response-unavailable")
            XCTAssertEqual(app.staticTexts["fixture.signin.diagnostic"].label,
                           "signIn|200|69169169-1691-4691-8691-691691691691")
            XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch.exists)
            try app.performAccessibilityAudit(for: .all)
        } else {
            let answer = app.staticTexts.matching(identifier: "lio.answer")
                .matching(NSPredicate(format: "label == %@", "Existing Lio answer")).firstMatch
            XCTAssertTrue(answer.waitForExistence(timeout: 20))
            XCTAssertEqual(app.staticTexts["fixture.signin.state"].label, "signed-in")
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            composer.tap(); composer.typeText("Unsent sign-in regression draft")
            XCTAssertEqual(composer.value as? String, "Unsent sign-in regression draft")
            app.terminate(); app.launch()
            XCTAssertTrue(answer.waitForExistence(timeout: 20))
            XCTAssertEqual(composer.value as? String, "Unsent sign-in regression draft")
            XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        }
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "sign-in-result-__SIGNIN_LANGUAGE__"
        attachment.lifetime = .keepAlways; add(attachment)
    }
}
