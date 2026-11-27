import XCTest

/// #2004 Stay: only collected hotels, filtered by price band; "Add to trip" gives a notice.
@MainActor extension LioToolsUITests {
    @objc func testStayListsCollectedHotelsAndFiltersByPrice() throws {
        continueAfterFailure = false
        func capture(_ app: XCUIApplication, _ name: String) {
            let screenshot = XCTAttachment(screenshot: app.screenshot())
            screenshot.name = name
            screenshot.lifetime = .keepAlways
            add(screenshot)
        }
        for (language, appearance) in [("en", "light"), ("zh-Hans", "dark")] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-place-tools-acceptance", "-cj.ui.language.v1", language,
                                   "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                   "UICTContentSizeCategoryL"]
            app.launch()
            defer { app.terminate() }
            XCTAssertTrue(app.descendants(matching: .any)["lio.places.development-banner"].waitForExistence(timeout: 8))
            func count() -> Int {
                app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'lio.stay.open.'")).count
            }
            XCTAssertEqual(count(), 4)
            capture(app, "stay-all-\(language)-\(appearance)")
            app.buttons["lio.stay.band.500-1000"].tap()
            XCTAssertEqual(count(), 1)
            XCTAssertTrue(app.buttons["lio.stay.open.pl_bj_b"].exists)
            app.buttons["lio.stay.city.shanghai"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["lio.stay.empty"].waitForExistence(timeout: 4))
            capture(app, "stay-empty-\(language)-\(appearance)")
            app.buttons["lio.stay.reset"].tap()
            XCTAssertEqual(count(), 4)
            app.buttons["lio.stay.add.pl_bj_a"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["lio.place.added"].waitForExistence(timeout: 4))
            capture(app, "stay-added-\(language)-\(appearance)")
        }
    }

    /// #2005 Explore: of what AMap finds nearby, only places in our library are listed, best first.
    @objc func testExploreKeepsOnlyCollectedPlacesNearby() throws {
        continueAfterFailure = false
        func capture(_ app: XCUIApplication, _ name: String) {
            let screenshot = XCTAttachment(screenshot: app.screenshot())
            screenshot.name = name
            screenshot.lifetime = .keepAlways
            add(screenshot)
        }
        for (language, appearance) in [("en", "light"), ("zh-Hans", "dark")] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-explore-acceptance", "-cj.ui.language.v1", language,
                                   "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                   "UICTContentSizeCategoryL"]
            app.launch()
            func count() -> Int {
                app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'lio.explore.open.'")).count
            }
            XCTAssertTrue(app.descendants(matching: .any)["lio.places.development-banner"].waitForExistence(timeout: 8))
            // Within 1 km: the duck restaurant and the department store; the street stall and the corner shop are
            // not in our library, and the Palace Museum is 1.25 km away.
            XCTAssertTrue(app.buttons["lio.explore.open.pl_bj_quanjude"].waitForExistence(timeout: 8))
            XCTAssertEqual(count(), 2)
            XCTAssertTrue(app.buttons["lio.explore.open.pl_bj_wangfujing"].exists)
            capture(app, "explore-1km-\(language)-\(appearance)")
            // Best first: the department store (rank 1) before the restaurant (rank 2).
            XCTAssertLessThan(app.buttons["lio.explore.open.pl_bj_wangfujing"].frame.minY,
                              app.buttons["lio.explore.open.pl_bj_quanjude"].frame.minY)
            app.buttons["3 km"].tap()
            XCTAssertTrue(app.buttons["lio.explore.open.pl_bj_gugong"].waitForExistence(timeout: 6))
            XCTAssertEqual(count(), 3)
            // Only sights.
            app.buttons["lio.explore.kind.food"].tap()
            app.buttons["lio.explore.kind.shopping"].tap()
            XCTAssertTrue(app.buttons["lio.explore.open.pl_bj_gugong"].waitForExistence(timeout: 6))
            XCTAssertEqual(count(), 1)
            capture(app, "explore-sights-\(language)-\(appearance)")
            // Nothing chosen.
            app.buttons["lio.explore.kind.sights"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["lio.explore.choose"].waitForExistence(timeout: 4))
            app.terminate()
        }
    }

    @objc func testExploreSaysSoWhenTheLibraryIsEmpty() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-explore-acceptance", "--lio-explore-empty-library",
                               "-cj.ui.language.v1", "en", "-lio.ui.appearance.v1", "light"]
        app.launch()
        defer { app.terminate() }
        XCTAssertTrue(app.descendants(matching: .any)["lio.explore.library-empty"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.descendants(matching: .any)["lio.places.development-banner"].exists)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "explore-library-empty-en"
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }

    /// #2004, #2005 entries: with the switch on, the Stay card opens the library's Stay page and the Eat & Play hub's
    /// nearby row opens Explore; the old pages stay behind the switch being off.
    @objc func testToolsEntriesOpenStayAndExploreWhenSwitchedOn() throws {
        continueAfterFailure = false
        let base = ["--lio-preview", "--lio-tools-preview", "--lio-tools-all-cards", "--lio-nearby-preview",
                    "-cj.ui.language.v1", "en", "-lio.ui.appearance.v1", "light"]
        func launch(_ extra: [String]) -> XCUIApplication {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = base + extra
            app.launch()
            XCTAssertTrue(app.tabBars.buttons["Tools"].waitForExistence(timeout: 8))
            app.tabBars.buttons["Tools"].tap()
            return app
        }
        let on = launch(["--lio-place-tools-preview"])
        let stay = on.buttons["lio.tools.hotels"]
        XCTAssertTrue(stay.waitForExistence(timeout: 6))
        stay.tap()
        let page = on.descendants(matching: .any).matching(NSPredicate(
            format: "identifier == 'lio.stay.library-empty' OR identifier == 'lio.stay.filters.city'")).firstMatch
        XCTAssertTrue(page.waitForExistence(timeout: 8))
        XCTAssertFalse(on.textFields["lio.hotels.city"].exists)
        on.navigationBars.buttons.firstMatch.tap()
        on.buttons["lio.tools.eat-play"].tap()
        let nearby = on.buttons["lio.tools.nearby"]
        XCTAssertTrue(nearby.waitForExistence(timeout: 6))
        nearby.tap()
        XCTAssertTrue(on.descendants(matching: .any).matching(NSPredicate(
            format: "identifier BEGINSWITH 'lio.explore.'")).firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(on.descendants(matching: .any)["lio.nearby.group"].exists)
        let shot = XCTAttachment(screenshot: on.screenshot())
        shot.name = "entry-explore-on"
        shot.lifetime = .keepAlways
        add(shot)
        on.terminate()

        let off = launch([])
        defer { off.terminate() }
        off.buttons["lio.tools.eat-play"].tap()
        off.buttons["lio.tools.nearby"].tap()
        XCTAssertTrue(off.descendants(matching: .any).matching(NSPredicate(
            format: "identifier BEGINSWITH 'lio.nearby.'")).firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(off.descendants(matching: .any).matching(NSPredicate(
            format: "identifier BEGINSWITH 'lio.explore.'")).firstMatch.exists)
    }
}
