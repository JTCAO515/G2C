import XCTest

@MainActor final class LioWarmSessionUITests: XCTestCase {
    func testWarmSessionKeepsConversationAndDraftInBothLanguagesAndAppearances() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.warm-session.acceptance")
                app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                       "-lio.ui.appearance.v1", appearance]
                app.launch()
                defer { app.terminate() }
                let answer = app.staticTexts["lio.answer"].firstMatch
                XCTAssertTrue(answer.waitForExistence(timeout: 8))
                XCTAssertEqual(answer.label, "Existing answer")
                let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
                composer.tap(); composer.typeText("Unsent draft")
                app.buttons["fixture.session.suspend"].tap()
                XCTAssertTrue(app.otherElements["lio.session.recovery.banner"].waitForExistence(timeout: 5))
                XCTAssertEqual(answer.label, "Existing answer")
                XCTAssertEqual(composer.value as? String, "Unsent draft")
                XCTAssertFalse(app.buttons["lio.send"].isEnabled)
                XCTAssertFalse(app.staticTexts["lio.opening"].exists)
                app.buttons["fixture.session.offline"].tap()
                let retry = app.buttons["lio.session.retry"]
                XCTAssertTrue(retry.waitForExistence(timeout: 5))
                XCTAssertEqual(answer.label, "Existing answer")
                retry.tap()
                let renewed = app.staticTexts.matching(identifier: "lio.answer").matching(NSPredicate(format: "label == %@", "Details after renewal")).firstMatch
                XCTAssertTrue(renewed.waitForExistence(timeout: 8))
                XCTAssertEqual(composer.value as? String, "Unsent draft")
                XCTAssertFalse(app.otherElements["lio.session.recovery.banner"].exists)
                XCTAssertEqual(app.textViews.matching(identifier: "lio.question").count, 2)
                XCTAssertFalse(app.staticTexts["lio.opening"].exists)
                let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", chinese ? "回复已完成" : "Reply complete"), object: renewed)
                XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 8), .completed)
                try app.performAccessibilityAudit(for: .all)
                let image = XCTAttachment(screenshot: app.screenshot())
                image.name = "warm-session-\(chinese ? "zh" : "en")-\(appearance)"; image.lifetime = .keepAlways; add(image)
                app.terminate()
            }
        }
    }
    func testEarlierChatFailureDoesNotMaskTheNextSessionRetryInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.warm-session.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", "light"]
            app.launch()
            defer { app.terminate() }
            XCTAssertTrue(app.staticTexts["lio.answer"].firstMatch.waitForExistence(timeout: 8))
            app.buttons["lio.chat.newShortcut"].tap()
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "1"), object: app.staticTexts["fixture.session.new-chats"])], timeout: 5), .completed)
            XCTAssertTrue(app.staticTexts["lio.answer"].firstMatch.waitForExistence(timeout: 5))
            app.buttons["fixture.session.read-failure"].tap()
            XCTAssertTrue(app.buttons["lio.session.retry"].waitForExistence(timeout: 5))
            app.buttons["fixture.session.suspend"].tap()
            app.buttons["fixture.session.offline"].tap()
            app.buttons["lio.session.retry"].tap()
            let observed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "1"), object: app.staticTexts["fixture.session.reconnects"])
            XCTAssertEqual(XCTWaiter.wait(for: [observed], timeout: 5), .completed)
            XCTAssertEqual(app.staticTexts["lio.answer"].firstMatch.label, "Existing answer")
            app.terminate()
        }
    }

    func testTripsKeepTheirTabAndUseTheRenewedReaderInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.warm-session.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", "light"]
            app.launch()
            defer { app.terminate() }
            let tab = app.tabBars.buttons[chinese ? "行程" : "Trips"]
            tab.tap()
            XCTAssertTrue(app.staticTexts["Trip before renewal"].waitForExistence(timeout: 8))
            app.buttons["fixture.session.suspend"].tap()
            app.buttons["fixture.session.offline"].tap()
            app.buttons["lio.session.retry"].tap()
            XCTAssertTrue(app.staticTexts["Trip after renewal"].waitForExistence(timeout: 8))
            XCTAssertTrue(tab.isSelected)
            XCTAssertFalse(app.staticTexts["Trip before renewal"].exists)
            try app.performAccessibilityAudit(for: .all)
            app.terminate()
        }
    }

}
