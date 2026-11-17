import XCTest

@MainActor final class LioSignInUITests: XCTestCase {
    func testLioSignInWithoutLegacyStarterData() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchEnvironment = ["B691_LOCAL_ENDPOINT": "__SIGNIN_ENDPOINT__"]
        app.launchArguments = ["-cj.ui.language.v1", "__SIGNIN_LANGUAGE__",
                               "-lio.ui.appearance.v1", "__SIGNIN_APPEARANCE__"]
        app.launch()
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
