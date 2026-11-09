import XCTest

@MainActor final class LioHomeUITests: XCTestCase {
    func testEnglish() throws { try exercise("en", question: "How do I take the metro in Shanghai?", source: "Source") }
    func testChinese() throws { try exercise("zh-Hans", question: "在上海怎么坐地铁？", source: "来源") }

    func testTripEnglish() throws {
        try exerciseTrip("en", clarification: "For three days in Beijing", trips: "Trips", day: "Day 1", fixed: "Hotel check-in")
    }

    func testTripChinese() throws {
        try exerciseTrip("zh-Hans", clarification: "北京三天", trips: "行程", day: "第 1 天", fixed: "酒店入住")
    }

    private func exerciseTrip(_ language: String, clarification: String, trips: String, day: String, fixed: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.1"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        sample.tap()
        app.buttons["lio.send"].tap()
        let reply = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", clarification)).firstMatch
        XCTAssertTrue(reply.waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["lio.trip.show"].exists)

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap()
        composer.typeText("slow")
        app.buttons["lio.send"].tap()
        let show = app.buttons["lio.trip.show"]
        XCTAssertTrue(show.waitForExistence(timeout: 12))
        XCTAssertFalse(app.staticTexts[fixed].exists)

        let disclosure = app.descendants(matching: .any).matching(identifier: "lio.trip.day.1").firstMatch
        XCTAssertTrue(disclosure.waitForExistence(timeout: 6), app.debugDescription)
        disclosure.tap()
        XCTAssertTrue(app.staticTexts[fixed].waitForExistence(timeout: 6))
        disclosure.tap()
        show.tap()

        XCTAssertTrue(app.navigationBars[trips].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts[fixed].exists)
        app.buttons["lio.trip.map.1"].tap()
        XCTAssertTrue(app.navigationBars[day].waitForExistence(timeout: 8))
    }

    private func exercise(_ language: String, question: String, source title: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
        XCTAssertTrue(app.staticTexts["Lio"].exists)
        XCTAssertFalse(app.navigationBars.firstMatch.exists)
        XCTAssertTrue(app.tabBars.buttons[language == "en" ? "Trips" : "行程"].exists)
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.isHittable)
        try app.performAccessibilityAudit(for: .all)

        sample.tap()
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertEqual(composer.value as? String, question)
        XCTAssertFalse(app.staticTexts["lio.question"].exists)
        XCTAssertTrue(app.buttons["lio.send"].isEnabled)
        app.buttons["lio.send"].tap()

        XCTAssertTrue(app.staticTexts["lio.question"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["lio.answer"].waitForExistence(timeout: 8))
        let source = app.buttons["lio.source"]
        XCTAssertTrue(source.waitForExistence(timeout: 8))
        XCTAssertTrue(source.isHittable)
        source.tap()
        XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 8))
        XCTAssertFalse(app.links.firstMatch.exists)
    }
}
