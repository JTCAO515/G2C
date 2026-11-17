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
            if "__WARM_COLD_FAULT__" == "1" {
                app.buttons["fixture.root.offline"].tap()
                waitForMode("offline", app: app)
            }
            app.terminate()
            app.launch()
            if "__WARM_COLD_FAULT__" == "1" {
                XCTAssertTrue(app.buttons["lio.session.retry"].waitForExistence(timeout: 20))
                XCTAssertFalse(app.secureTextFields["demo.invite.code"].exists)
                XCTAssertFalse(existing.exists)
                XCTAssertEqual(app.staticTexts["fixture.root.sdk-presence"].label, "present")
                XCTAssertEqual(app.staticTexts["fixture.root.problem"].label, "__WARM_EXPECTED_PROBLEM__")
                XCTAssertEqual(app.staticTexts["fixture.root.category"].label, "__WARM_EXPECTED_CATEGORY__")
                XCTAssertNotEqual(app.staticTexts["fixture.root.mode"].label, "ready", "No Allow ACK has arrived in this process")
                app.buttons["fixture.root.allow"].tap()
                waitForMode("ready", app: app)
                app.buttons["lio.session.retry"].tap()
            }
            XCTAssertTrue(existing.waitForExistence(timeout: 20))
            XCTAssertEqual(composer.value as? String, "Unsent root draft")
            XCTAssertEqual(app.staticTexts["fixture.root.bootstrap"].label, "restore")
            XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        }
        app.buttons["fixture.root.hold"].tap()
        waitForMode("hold", app: app)
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
        waitForMode("offline", app: app)
        XCTAssertTrue(app.buttons["lio.session.retry"].waitForExistence(timeout: 12))
        XCTAssertEqual(app.staticTexts["fixture.root.problem"].label, "__WARM_EXPECTED_PROBLEM__")
        XCTAssertEqual(app.staticTexts["fixture.root.category"].label, "__WARM_EXPECTED_CATEGORY__")
        XCTAssertTrue(existing.exists)
        XCTAssertEqual(composer.value as? String, "Unsent root draft")
        app.buttons["fixture.root.allow"].tap()
        waitForMode("ready", app: app)
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
        waitForMode("denied", app: app)
        if "__WARM_DENY_COLD__" == "1" {
            app.terminate(); app.launch()
        } else {
            XCUIDevice.shared.press(.home); app.activate()
        }
        XCTAssertTrue(app.secureTextFields["demo.invite.code"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["fixture.root.retained"].label, "empty")
        XCTAssertFalse(other.exists)
    }
    private func waitForMode(_ mode: String, app: XCUIApplication) {
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", mode),
            object: app.staticTexts["fixture.root.mode"])
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 5), .completed)
    }

}
