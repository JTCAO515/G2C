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

    /// #1748 (W4-4): with the in-app location choice on, Taxi reads nothing until the traveller allows it; "Not now"
    /// leaves the pickup to be chosen by hand; turning it off in Me → Location asks again next time.
    @objc func testLocationConsentGatesTaxiPickupInBothLanguages() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let en = language == "en"
            let app = taxiFixture(language: language, extraArguments: ["--lio-location-consent-preview"])
            func shot(_ name: String) {
                let a = XCTAttachment(screenshot: app.screenshot()); a.name = "location-consent-\(name)-\(language)"
                a.lifetime = .keepAlways; add(a)
            }
            let pickup = app.buttons["lio.taxi.pickup"]
            let use = app.buttons["lio.location.use"]
            XCTAssertTrue(use.waitForExistence(timeout: 6), app.debugDescription)
            XCTAssertTrue(app.staticTexts[en ? "Choose a pickup point, or use your location." : "请选择起点，或使用你的位置。"].exists)
            XCTAssertFalse(pickup.label.contains(en ? "Beijing Railway Station" : "北京站"), "nothing read before the choice")
            shot("1-taxi-before")

            use.tap()
            let allow = app.buttons["lio.location-consent.allow"]
            XCTAssertTrue(allow.waitForExistence(timeout: 5), app.debugDescription)
            for point in ["purpose", "when", "where", "keep", "change", "without"] {
                XCTAssertTrue(app.descendants(matching: .any)["lio.location-consent.\(point)"].exists, point)
            }
            XCTAssertTrue(app.staticTexts[en ? "Use your location?" : "使用你的位置？"].exists)
            shot("2-choice")
            app.buttons["lio.location-consent.decline"].tap()
            XCTAssertTrue(allow.waitForNonExistence(timeout: 5))
            XCTAssertTrue(use.waitForExistence(timeout: 5), "declining keeps the manual pickup and the button")
            XCTAssertFalse(pickup.label.contains(en ? "Beijing Railway Station" : "北京站"))

            use.tap()
            XCTAssertTrue(allow.waitForExistence(timeout: 5))
            allow.tap()
            let located = NSPredicate(format: "label CONTAINS %@", en ? "Beijing Railway Station" : "北京站")
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: located, object: pickup)], timeout: 8),
                           .completed, app.debugDescription)
            XCTAssertFalse(use.exists)
            shot("3-taxi-after-allow")

            app.tabBars.buttons[en ? "Me" : "我的"].tap()
            let row = app.buttons["lio.me.location"]
            XCTAssertTrue(row.waitForExistence(timeout: 5), app.debugDescription)
            row.tap()
            let off = app.buttons["lio.location-settings.off"]
            XCTAssertTrue(off.waitForExistence(timeout: 5), app.debugDescription)
            shot("4-me-location-on")
            off.tap()
            XCTAssertTrue(app.buttons["lio.location.use"].waitForExistence(timeout: 5), "turned off: the page offers it again")
            XCTAssertTrue(app.descendants(matching: .any)["lio.location-settings.status"].label
                .contains(en ? "Location is off" : "位置已关闭"))
            shot("5-me-location-off")

            app.tabBars.buttons[en ? "Tools" : "工具"].tap()
            let back = app.navigationBars.buttons.element(boundBy: 0)
            if back.waitForExistence(timeout: 3) && !app.buttons["lio.tools.taxi"].exists { back.tap() }
            XCTAssertTrue(app.buttons["lio.tools.taxi"].waitForExistence(timeout: 5), app.debugDescription)
            app.buttons["lio.tools.taxi"].tap()
            XCTAssertTrue(app.buttons["lio.location.use"].waitForExistence(timeout: 6), "asks again after turning it off")
            XCTAssertFalse(app.buttons["lio.taxi.pickup"].label.contains(en ? "Beijing Railway Station" : "北京站"))
            shot("6-taxi-asks-again")
            app.terminate()
        }
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
                             scenario: String? = nil, showGuide: Bool = false,
                             extraArguments: [String] = []) -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-taxi-preview",
                               "-cj.ui.language.v1", language, "-lio.ui.appearance.v1", appearance,
                               "-lio.taxi.seen-guide.v1", showGuide ? "NO" : "YES"]
        if let scenario { app.launchArguments.append("--lio-taxi-preview-\(scenario)") }
        app.launchArguments += extraArguments
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
