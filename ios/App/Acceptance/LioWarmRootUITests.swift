import XCTest

@MainActor final class LioWarmRootUITests: XCTestCase {
    func testActualRootRetainsOnlyTheSameOwnerAndRetiresItsOriginalClients() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.app")
        app.launchEnvironment["B691_LOCAL_ENDPOINT"] = "__WARM_ENDPOINT__"
        app.launchArguments = ["-cj.ui.language.v1", "__WARM_LANGUAGE__", "-lio.ui.appearance.v1", "light"]
        app.launch()
        defer { app.terminate() }
        let existing = app.staticTexts.matching(identifier: "lio.answer").matching(NSPredicate(format: "label == %@", "Existing owner A answer")).firstMatch
        XCTAssertTrue(existing.waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap(); composer.typeText("Unsent root draft")
        if "__WARM_COLD_RESTART__" == "1" {
            app.terminate()
            app.launch()
            XCTAssertTrue(existing.waitForExistence(timeout: 20))
            XCTAssertEqual(composer.value as? String, "Unsent root draft")
            XCTAssertEqual(app.staticTexts["fixture.root.bootstrap"].label, "restore")
            XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        }
        app.buttons["fixture.root.hold"].tap()
        // Actual iOS lifecycle -> production DemoBetaRootView -> actual account host.
        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(app.otherElements["lio.session.recovery.banner"].waitForExistence(timeout: 10))
        XCTAssertTrue(existing.exists)
        XCTAssertEqual(composer.value as? String, "Unsent root draft")
        XCTAssertEqual(app.staticTexts["fixture.root.business"].label, "retired")
        XCTAssertEqual(app.staticTexts["fixture.root.retained"].label, "retained")
        XCTAssertEqual(app.staticTexts["fixture.root.display"].label, "same")
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)
        app.buttons["fixture.root.offline"].tap()
        XCTAssertTrue(app.buttons["lio.session.retry"].waitForExistence(timeout: 12))
        XCTAssertEqual(app.staticTexts["fixture.root.problem"].label, "503|sessionCheck|69169169-1691-4691-8691-691691691691")
        XCTAssertTrue(existing.exists)
        XCTAssertEqual(composer.value as? String, "Unsent root draft")
        app.buttons["fixture.root.allow"].tap()
        app.buttons["lio.session.retry"].tap()
        let resumed = app.staticTexts.matching(identifier: "lio.answer").matching(NSPredicate(format: "label == %@", "Same owner after renewal")).firstMatch
        XCTAssertTrue(resumed.waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["fixture.root.display"].label, "same")
        XCTAssertEqual(app.staticTexts["fixture.root.trip"].label, "new")
        XCTAssertEqual(composer.value as? String, "Unsent root draft")
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        let evidence = XCTAttachment(screenshot: app.screenshot()); evidence.name = "actual-root-same-owner"; evidence.lifetime = .keepAlways; add(evidence)

        app.buttons["fixture.root.other"].tap()
        let other = app.staticTexts.matching(identifier: "lio.answer").matching(NSPredicate(format: "label == %@", "Independent owner B answer")).firstMatch
        XCTAssertTrue(other.waitForExistence(timeout: 20))
        XCTAssertFalse(existing.exists)
        XCTAssertFalse(resumed.exists)
        XCTAssertEqual(composer.value as? String, "")
        XCTAssertEqual(app.staticTexts["fixture.root.display"].label, "changed")
        app.buttons["fixture.root.deny"].tap()
        XCUIDevice.shared.press(.home); app.activate()
        XCTAssertTrue(app.secureTextFields["demo.invite.code"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["fixture.root.retained"].label, "empty")
        XCTAssertFalse(other.exists)
    }
}
