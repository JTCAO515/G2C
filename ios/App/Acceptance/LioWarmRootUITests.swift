import XCTest

@MainActor final class LioWarmRootUITests: XCTestCase {
    func testColdAuthoritativeDenialKeepsItsOwnSafeProblemRecord() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.app")
        app.launchEnvironment = ["B691_LOCAL_ENDPOINT": "__WARM_ENDPOINT__", "B691_COLD_DENIAL_NOTES": "1"]
        app.launchArguments = ["-cj.ui.language.v1", "__WARM_LANGUAGE__", "-lio.ui.appearance.v1", "light"]
        app.launch()
        defer { app.terminate() }
        let answer = app.staticTexts.matching(identifier: "lio.answer")
            .matching(NSPredicate(format: "label == %@", "Existing owner A answer")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap(); composer.typeText("Draft before cold denial")
        app.buttons["fixture.root.deny"].tap()
        waitForMode("denied", app: app)
        app.terminate(); app.launch()
        XCTAssertTrue(app.secureTextFields["demo.invite.code"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["fixture.root.bootstrap"].label, "restore")
        XCTAssertEqual(app.staticTexts["fixture.root.retained"].label, "empty")
        XCTAssertFalse(answer.exists)
        XCTAssertFalse(composer.exists)
        app.buttons["fixture.root.inspect-problem"].tap()
        XCTAssertEqual(app.staticTexts["fixture.root.inspected-problem"].label,
                       "signIn|sessionCheck|http|0|__WARM_DENIAL_STATUS__|__WARM_TRACE__")
        let evidence = XCTAttachment(screenshot: app.screenshot())
        evidence.name = "cold-authoritative-denial-note"; evidence.lifetime = .keepAlways; add(evidence)
    }

    func testNativeLockScreenReturnsToTheSameChatAndDraftAfterAReadFailure() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.app")
        app.launchEnvironment["B691_LOCAL_ENDPOINT"] = "__WARM_ENDPOINT__"
        app.launchEnvironment["B691_LOCK_SCREEN"] = "1"
        app.launchArguments = ["-cj.ui.language.v1", "__WARM_LANGUAGE__", "-lio.ui.appearance.v1", "light"]
        app.launch()
        defer { app.terminate() }
        let answer = app.staticTexts.matching(identifier: "lio.answer")
            .matching(NSPredicate(format: "label == %@", "Existing owner A answer")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap(); composer.typeText("Draft before native lock")
        app.buttons["fixture.root.offline"].tap()
        waitForMode("offline", app: app)
        try nativeLockAndReturn(app)
        XCTAssertTrue(app.buttons["lio.session.retry"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.staticTexts["fixture.root.bootstrap"].label, "sign-in")
        XCTAssertEqual(app.staticTexts["fixture.root.sdk-presence"].label, "present")
        XCTAssertEqual(app.staticTexts["fixture.root.problem"].label, "__WARM_EXPECTED_PROBLEM__")
        XCTAssertEqual(app.staticTexts["fixture.root.category"].label, "__WARM_EXPECTED_CATEGORY__")
        XCTAssertTrue(answer.exists)
        XCTAssertEqual(composer.value as? String, "Draft before native lock")
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        app.buttons["fixture.root.allow"].tap()
        waitForMode("ready", app: app)
        app.buttons["lio.session.retry"].tap()
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        XCTAssertEqual(composer.value as? String, "Draft before native lock")
        XCTAssertEqual(app.staticTexts["fixture.root.display"].label, "same")
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        let recovered = XCTAttachment(screenshot: app.screenshot())
        recovered.name = "native-lock-recovered"; recovered.lifetime = .keepAlways; add(recovered)
    }

    func testNativeLockScreenWithAuthoritativeDenialReturnsToSignIn() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.app")
        app.launchEnvironment = ["B691_LOCAL_ENDPOINT": "__WARM_ENDPOINT__", "B691_LOCK_SCREEN": "1", "B691_TIMELINE_TIMEOUT": "1"]
        app.launchArguments = ["-cj.ui.language.v1", "__WARM_LANGUAGE__", "-lio.ui.appearance.v1", "light"]
        app.launch()
        defer { app.terminate() }
        let answer = app.staticTexts.matching(identifier: "lio.answer")
            .matching(NSPredicate(format: "label == %@", "Existing owner A answer")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap(); composer.typeText("Draft before authoritative denial")
        app.buttons["fixture.root.deny"].tap()
        waitForMode("denied", app: app)
        try nativeLockAndReturn(app)
        XCTAssertTrue(app.secureTextFields["demo.invite.code"].waitForExistence(timeout: 20))
        XCTAssertFalse(answer.exists)
        XCTAssertFalse(composer.exists)
        XCTAssertEqual(app.staticTexts["fixture.root.retained"].label, "empty")
        app.buttons["fixture.root.inspect-problem"].tap()
        XCTAssertEqual(app.staticTexts["fixture.root.inspected-problem"].label,
                       "signIn|sessionCheck|http|0|__WARM_DENIAL_STATUS__|__WARM_TRACE__")
        let evidence = XCTAttachment(screenshot: app.screenshot())
        evidence.name = "native-lock-authoritative-denial"; evidence.lifetime = .keepAlways; add(evidence)
    }

    func testNativeLockScreenTimelineTimeoutRetainsConversationAndDraft() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.app")
        app.launchEnvironment = ["B691_LOCAL_ENDPOINT": "__WARM_ENDPOINT__", "B691_LOCK_SCREEN": "1", "B691_TIMELINE_TIMEOUT": "1"]
        app.launchArguments = ["-cj.ui.language.v1", "__WARM_LANGUAGE__", "-lio.ui.appearance.v1", "light"]
        app.launch()
        defer { app.terminate() }
        let answer = app.staticTexts.matching(identifier: "lio.answer")
            .matching(NSPredicate(format: "label == %@", "Existing owner A answer")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap(); composer.typeText("Draft before native timeline timeout")
        app.buttons["fixture.root.timeline-timeout"].tap()
        waitForMode("timeline-timeout", app: app)
        try nativeLockAndReturn(app)
        XCTAssertTrue(app.buttons["lio.read.retry"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.secureTextFields["demo.invite.code"].exists)
        XCTAssertTrue(answer.exists)
        XCTAssertEqual(composer.value as? String, "Draft before native timeline timeout")
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        app.buttons["fixture.root.inspect-problem"].tap()
        XCTAssertEqual(app.staticTexts["fixture.root.inspected-problem"].label, "network|timeline|network|-1001|0|-")
        app.buttons["fixture.root.allow"].tap()
        waitForMode("ready", app: app)
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.buttons["lio.read.retry"])
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 20), .completed)
        XCTAssertEqual(composer.value as? String, "Draft before native timeline timeout")
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        let evidence = XCTAttachment(screenshot: app.screenshot())
        evidence.name = "native-lock-timeline-timeout-recovered"; evidence.lifetime = .keepAlways; add(evidence)
    }

    func testColdTimelineTimeoutKeepsTheSessionAndDraftAndNamesTheReadStage() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.app")
        app.launchEnvironment["B691_LOCAL_ENDPOINT"] = "__WARM_ENDPOINT__"
        app.launchEnvironment["B691_TIMELINE_TIMEOUT"] = "1"
        app.launchArguments = ["-cj.ui.language.v1", "__WARM_LANGUAGE__", "-lio.ui.appearance.v1", "light"]
        app.launch()
        defer { app.terminate() }
        let answer = app.staticTexts.matching(identifier: "lio.answer")
            .matching(NSPredicate(format: "label == %@", "Existing owner A answer")).firstMatch
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap(); composer.typeText("Draft before timeline timeout")
        app.buttons["fixture.root.timeline-timeout"].tap()
        waitForMode("timeline-timeout", app: app)
        app.terminate(); app.launch()
        XCTAssertTrue(app.buttons["lio.read.retry"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.secureTextFields["demo.invite.code"].exists)
        XCTAssertEqual(app.staticTexts["fixture.root.sdk-presence"].label, "present")
        XCTAssertEqual(app.staticTexts["fixture.root.business"].label, "active")
        XCTAssertEqual(app.staticTexts["fixture.root.bootstrap"].label, "restore")
        XCTAssertEqual(composer.value as? String, "Draft before timeline timeout")
        XCTAssertFalse(answer.exists)
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        app.buttons["fixture.root.inspect-problem"].tap()
        XCTAssertEqual(app.staticTexts["fixture.root.inspected-problem"].label, "network|timeline|network|-1001|0|-")
        let failure = XCTAttachment(screenshot: app.screenshot())
        failure.name = "cold-first-timeline-timeout"; failure.lifetime = .keepAlways; add(failure)
        let retry = app.buttons["lio.read.retry"]
        retry.tap()
        let reading = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: retry)
        XCTAssertEqual(XCTWaiter.wait(for: [reading], timeout: 5), .completed)
        XCTAssertTrue(retry.waitForExistence(timeout: 20))
        app.buttons["fixture.root.allow"].tap()
        waitForMode("ready", app: app)
        // The production reader polls and can recover before a second tap.
        XCTAssertTrue(answer.waitForExistence(timeout: 20))
        XCTAssertEqual(composer.value as? String, "Draft before timeline timeout")
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        let recovered = XCTAttachment(screenshot: app.screenshot())
        recovered.name = "cold-first-timeline-timeout-recovered"; recovered.lifetime = .keepAlways; add(recovered)
    }

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
    private func nativeLockAndReturn(_ app: XCUIApplication) throws {
        XCUIDevice.shared.press(.home)
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        XCTAssertTrue(springboard.wait(for: .runningForeground, timeout: 10))
        // Start the single hardware action only after XCTest has finished Home.
        // The reply acknowledges the actual native lock state and cover sheet.
        try waitForNativeControl("lock")
        let sheet = springboard.descendants(matching: .any).matching(identifier: "SBCoverSheetWindow").firstMatch
        XCTAssertTrue(sheet.waitForExistence(timeout: 10), "Must observe the actual native lock-screen window")
        let locked = XCTAttachment(screenshot: springboard.screenshot())
        locked.name = "native-lock-screen"; locked.lifetime = .keepAlways; add(locked)
        let bottom = springboard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.99))
        let upper = springboard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.35))
        bottom.press(forDuration: 0.05, thenDragTo: upper, withVelocity: .fast, thenHoldForDuration: 0)
        // Verify native unlock before App activation; retained AX nodes are not readiness.
        try waitForNativeControl("observe-unlock")
        let home = XCTAttachment(screenshot: springboard.screenshot())
        home.name = "native-lock-home-after-unlock"; home.lifetime = .keepAlways; add(home)
        app.activate()
    }

    private func waitForNativeControl(_ action: String) throws {
        let unlocked = expectation(description: "Native simulator control acknowledged: \(action)")
        var request = URLRequest(url: try XCTUnwrap(URL(string: "__WARM_ENDPOINT__/fixture-lock-screen")))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["action": action])
        struct NativeUnlock: Decodable { let observed: Bool }
        let lookup = URLSession.shared.dataTask(with: request) { bytes, response, error in
            defer { unlocked.fulfill() }
            XCTAssertNil(error)
            XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
            do {
                let result = try JSONDecoder().decode(NativeUnlock.self, from: try XCTUnwrap(bytes))
                XCTAssertTrue(result.observed)
            } catch { XCTFail("Native simulator control response was not valid") }
        }
        lookup.resume()
        XCTAssertEqual(XCTWaiter.wait(for: [unlocked], timeout: 15), .completed)
        lookup.cancel()
    }

    private func waitForMode(_ mode: String, app: XCUIApplication) {
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", mode),
            object: app.staticTexts["fixture.root.mode"])
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 5), .completed)
    }

}
