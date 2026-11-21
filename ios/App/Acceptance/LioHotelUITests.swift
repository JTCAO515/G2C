import XCTest

@MainActor extension LioToolsUITests {
    @objc func testTaxiAndHotelsRemainUsableAtTheLargestTextSize() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-taxi-preview",
                               "--lio-hotels-preview", "-cj.ui.language.v1", "en", "-lio.ui.appearance.v1", "dark",
                               "-lio.taxi.seen-guide.v1", "YES", "-UIPreferredContentSizeCategoryName",
                               "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        defer { app.terminate() }
        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.taxi"].tap()
        let destination = app.buttons["lio.taxi.destination"]
        XCTAssertTrue(destination.waitForExistence(timeout: 6))
        XCTAssertTrue(destination.isHittable)
        let pickup = app.buttons["lio.taxi.pickup"]
        if !pickup.isHittable { app.swipeUp() }
        XCTAssertTrue(pickup.isHittable)
        let taxiImage = XCTAttachment(screenshot: app.screenshot())
        taxiImage.name = "taxi-maximum-text-dark"
        taxiImage.lifetime = .keepAlways
        add(taxiImage)

        app.navigationBars.buttons.firstMatch.tap()
        app.buttons["lio.tools.hotels"].tap()
        let city = app.textFields["lio.hotels.city"]
        XCTAssertTrue(city.waitForExistence(timeout: 6))
        XCTAssertTrue(city.isHittable)
        let find = app.buttons["lio.hotels.find"]
        for _ in 0..<5 {
            if find.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(find.isHittable)
        let hotelsImage = XCTAttachment(screenshot: app.screenshot())
        hotelsImage.name = "hotels-maximum-text-dark"
        hotelsImage.lifetime = .keepAlways
        add(hotelsImage)
    }

    @objc func testToolsFixtureOrdersTaxiAndHotelsBeforeTranslation() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-taxi-preview",
                               "--lio-hotels-preview", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        let taxi = app.buttons["lio.tools.taxi"]
        let hotels = app.buttons["lio.tools.hotels"]
        let translation = app.buttons["lio.tools.translation"]
        XCTAssertTrue(taxi.waitForExistence(timeout: 6))
        XCTAssertTrue(hotels.isHittable)
        XCTAssertTrue(translation.isHittable)
        XCTAssertLessThan(taxi.frame.minY, hotels.frame.minY)
        XCTAssertLessThan(hotels.frame.minY, translation.frame.minY)
    }

    @objc func testHotelsFixtureShowsFormAreaAndDisclosuresInBothLanguagesAndAppearances() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = hotelFixture(language: language, appearance: appearance)
                defer { app.terminate() }
                let find = app.buttons["lio.hotels.find"]
                let area = app.buttons["lio.hotels.area"]
                XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "lio.hotels.check-in").firstMatch.exists)
                XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "lio.hotels.check-out").firstMatch.exists)
                let guests = app.descendants(matching: .any).matching(identifier: "lio.hotels.guests").firstMatch
                XCTAssertTrue(guests.exists)
                XCTAssertEqual(guests.value as? String, "1")
                XCTAssertTrue(app.staticTexts[language == "en"
                    ? "Your trip suggests staying around Dongcheng" : "你的行程建议住在东城区一带"].exists)

                let expected = language == "en"
                    ? "Some links are affiliate links. If you book through them, Go2China may earn a commission at no extra cost to you."
                    : "部分链接为推广链接，你通过它预订时，Go2China 可能获得佣金，价格不受影响。"
                let findDisclosure = app.staticTexts["lio.hotels.find.disclosure"]
                let areaDisclosure = app.staticTexts["lio.hotels.area.disclosure"]
                XCTAssertEqual(findDisclosure.label, expected)
                XCTAssertGreaterThanOrEqual(findDisclosure.frame.minY, find.frame.maxY)
                XCTAssertEqual(areaDisclosure.label, expected)
                XCTAssertGreaterThanOrEqual(areaDisclosure.frame.minY, area.frame.maxY)
                XCTAssertEqual(app.staticTexts["lio.hotels.footer.disclosure"].label, expected)
                XCTAssertTrue(app.staticTexts[language == "en" ? "Booking and payment happen on Trip.com"
                                               : "预订和付款在 Trip.com 完成"].exists)

                let form = XCTAttachment(screenshot: app.screenshot())
                form.name = "hotels-form-\(language)-\(appearance)"
                form.lifetime = .keepAlways
                add(form)
                app.swipeUp()
                let footer = XCTAttachment(screenshot: app.screenshot())
                footer.name = "hotels-disclosures-\(language)-\(appearance)"
                footer.lifetime = .keepAlways
                add(footer)
            }
        }
    }

    @objc func testHotelsFixtureMakesUnappliedFiltersVisibleBeforeOpeningLink() {
        continueAfterFailure = false
        let app = hotelFixture(partial: true)
        defer { app.terminate() }
        let find = app.buttons["lio.hotels.find"]
        find.tap()
        let notice = app.staticTexts["lio.hotels.notice"]
        XCTAssertTrue(notice.waitForExistence(timeout: 5))
        XCTAssertEqual(notice.label, "Enter a city to search for hotels.")

        let field = app.textFields["lio.hotels.city"]
        field.tap()
        field.typeText("Beijing")
        app.swipeUp()
        find.tap()
        XCTAssertTrue(notice.waitForExistence(timeout: 5))
        XCTAssertEqual(notice.label, "On Trip.com, check guests.")
        let pickup = app.buttons["lio.hotels.partial-link"]
        XCTAssertTrue(pickup.exists)
        XCTAssertTrue(app.staticTexts["lio.hotels.partial-link.disclosure"].exists)
        pickup.tap()
        XCTAssertFalse(app.alerts.firstMatch.exists)
    }

    @objc func testHotelsFixtureCanSearchTheTripAreaWithoutTypingACity() {
        continueAfterFailure = false
        let app = hotelFixture(partial: true)
        defer { app.terminate() }
        let area = app.buttons["lio.hotels.area"]
        if !area.isHittable { app.swipeUp() }
        area.tap()
        let notice = app.staticTexts["lio.hotels.notice"]
        XCTAssertTrue(notice.waitForExistence(timeout: 5))
        XCTAssertEqual(notice.label, "On Trip.com, check guests.")
        XCTAssertTrue(app.buttons["lio.hotels.partial-link"].exists)
    }

    private func hotelFixture(language: String = "en", appearance: String = "light",
                              partial: Bool = false) -> XCUIApplication {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-hotels-preview",
                               "-cj.ui.language.v1", language, "-lio.ui.appearance.v1", appearance]
        if partial { app.launchArguments.append("--lio-hotels-preview-partial") }
        app.launch()
        let tools = app.tabBars.buttons[language == "en" ? "Tools" : "插件"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.hotels"].tap()
        XCTAssertTrue(app.textFields["lio.hotels.city"].waitForExistence(timeout: 6))
        return app
    }
}
