import XCTest

@MainActor extension LioToolsUITests {
    @objc func testTaxiFixtureEstimatesAndShowsDriverCard() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = taxiFixture(language: language, appearance: appearance)
                defer { app.terminate() }
                selectTaxiDestination(app, label: language == "en" ? "Summer Palace" : "颐和园")
                let estimate = app.buttons["lio.taxi.estimate"]
                XCTAssertTrue(estimate.isEnabled)
                estimate.tap()
                let price = app.staticTexts[language == "en"
                    ? "Final price is set by DiDi" : "以滴滴实际价格为准"]
                XCTAssertTrue(price.waitForExistence(timeout: 5))
                XCTAssertTrue(app.staticTexts["¥35–48"].exists)
                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "taxi-estimate-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)

                app.buttons["lio.taxi.driver"].tap()
                XCTAssertTrue(app.staticTexts["颐和园"].waitForExistence(timeout: 5))
                XCTAssertTrue(app.staticTexts["新建宫门路19号"].exists)
                XCTAssertTrue(app.staticTexts["Summer Palace"].exists)
                let card = XCTAttachment(screenshot: app.screenshot())
                card.name = "taxi-driver-\(language)-\(appearance)"
                card.lifetime = .keepAlways
                add(card)
            }
        }
    }

    @objc func testTaxiFixtureKeepsDriverCardWhenEstimateFailsAndOffersHandoffOptions() {
        continueAfterFailure = false
        let failures = [
            ("estimate-fails", "Taxi details aren’t available right now. Try again."),
            ("rate-limited", "Too many requests. Try again in a moment."),
            ("signed-out", "Sign in again, then try again."),
        ]
        for (scenario, notice) in failures {
            let app = taxiFixture(scenario: scenario)
            defer { app.terminate() }
            selectTaxiDestination(app, label: "Summer Palace")
            app.buttons["lio.taxi.estimate"].tap()
            XCTAssertTrue(app.staticTexts[notice].waitForExistence(timeout: 5))
            XCTAssertTrue(app.buttons["Try again"].exists)
            app.buttons["lio.taxi.driver"].tap()
            XCTAssertTrue(app.staticTexts["新建宫门路19号"].waitForExistence(timeout: 5))
        }

        let app = taxiFixture(scenario: "no-app")
        defer { app.terminate() }
        selectTaxiDestination(app, label: "Summer Palace")
        app.buttons["lio.taxi.handoff"].tap()
        XCTAssertTrue(app.buttons["Get DiDi in the App Store"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Use DiDi in Alipay"].isHittable)
        let driverOption = app.buttons.matching(NSPredicate(format: "label == %@ AND identifier != %@",
                                                            "Show the driver", "lio.taxi.driver")).firstMatch
        XCTAssertTrue(driverOption.exists)
    }

    @objc func testTaxiFixtureAllowsManualPickupAfterLocationDenial() {
        continueAfterFailure = false
        let app = taxiFixture(scenario: "location-denied")
        defer { app.terminate() }
        XCTAssertTrue(app.staticTexts["Location is unavailable. Choose a pickup point."].exists)
        selectTaxiDestination(app, label: "Summer Palace")
        XCTAssertFalse(app.buttons["lio.taxi.estimate"].isEnabled)
        app.buttons["lio.taxi.pickup"].tap()
        let field = app.textFields["Place name or address"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("Palace Museum")
        app.buttons["Search"].firstMatch.tap()
        let place = app.buttons.containing(.staticText, identifier: "Palace Museum").firstMatch
        XCTAssertTrue(place.waitForExistence(timeout: 5))
        place.tap()
        XCTAssertTrue(app.buttons["lio.taxi.estimate"].isEnabled)
    }

    @objc func testTaxiFirstUseGuideCanBeOpenedAgain() {
        continueAfterFailure = false
        let app = taxiFixture(showGuide: true)
        defer { app.terminate() }
        let englishSettings = app.staticTexts["In DiDi settings, switch the app language to English."]
        XCTAssertTrue(englishSettings.waitForExistence(timeout: 6))
        XCTAssertTrue(app.staticTexts["In DiDi payment settings, add your international card and check that it is accepted."].exists)
        XCTAssertTrue(app.staticTexts["In Alipay, search for the DiDi mini program and choose your ride there."].exists)
        app.navigationBars.buttons["Done"].tap()
        let guide = app.navigationBars.buttons["Taxi guide"]
        XCTAssertTrue(guide.waitForExistence(timeout: 5))
        guide.tap()
        XCTAssertTrue(englishSettings.waitForExistence(timeout: 5))
    }

    @objc func testTaxiSearchSelectionIsAvailableInRecentsAfterRelaunch() {
        continueAfterFailure = false
        let app = taxiFixture()
        defer { app.terminate() }
        app.buttons["lio.taxi.destination"].tap()
        let field = app.textFields["Place name or address"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("Summer Palace")
        app.buttons["Search"].firstMatch.tap()
        let found = app.buttons.matching(identifier: "lio.taxi.search-row").firstMatch
        XCTAssertTrue(found.waitForExistence(timeout: 5))
        XCTAssertTrue(found.label.contains("Summer Palace"))
        found.tap()
        XCTAssertTrue(app.buttons["lio.taxi.destination"].waitForExistence(timeout: 5))
        app.terminate()

        let reopened = taxiFixture()
        defer { reopened.terminate() }
        reopened.buttons["lio.taxi.destination"].tap()
        let recent = reopened.buttons.matching(identifier: "lio.taxi.recent-row").matching(
            NSPredicate(format: "label CONTAINS %@", "Summer Palace")
        ).firstMatch
        for _ in 0..<5 {
            if recent.isHittable { break }
            reopened.swipeUp()
        }
        XCTAssertTrue(recent.isHittable)
        recent.tap()
        let selected = reopened.buttons["lio.taxi.destination"]
        XCTAssertTrue(selected.waitForExistence(timeout: 5))
        XCTAssertTrue(selected.label.contains("Summer Palace"))
    }

    private func taxiFixture(language: String = "en", appearance: String = "light",
                             scenario: String? = nil, showGuide: Bool = false) -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-taxi-preview",
                               "-cj.ui.language.v1", language, "-lio.ui.appearance.v1", appearance,
                               "-lio.taxi.seen-guide.v1", showGuide ? "NO" : "YES"]
        if let scenario { app.launchArguments.append("--lio-taxi-preview-\(scenario)") }
        app.launch()
        let tools = app.tabBars.buttons[language == "en" ? "Tools" : "工具"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.taxi"].tap()
        if !showGuide {
            XCTAssertTrue(app.buttons["lio.taxi.destination"].waitForExistence(timeout: 6))
        }
        return app
    }

    private func selectTaxiDestination(_ app: XCUIApplication, label: String) {
        app.buttons["lio.taxi.destination"].tap()
        let place = app.buttons.containing(.staticText, identifier: label).firstMatch
        XCTAssertTrue(place.waitForExistence(timeout: 6))
        place.tap()
        XCTAssertTrue(app.buttons["lio.taxi.estimate"].waitForExistence(timeout: 6))
    }
}
