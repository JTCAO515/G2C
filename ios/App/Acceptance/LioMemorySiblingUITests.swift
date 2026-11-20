import XCTest

@MainActor final class LioMemorySiblingUITests: XCTestCase {
    func testMemoryEditorDoneKeepsTheUnsavedDraft() {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.memory-siblings.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-memory-titled-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        let remember = app.buttons.matching(identifier: "lio.memory.remember").firstMatch
        XCTAssertTrue(remember.waitForExistence(timeout: 10))
        remember.tap()
        app.tabBars.buttons["Memory"].tap()
        let card = app.buttons["lio.memory.card.luxury-hotel"]
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        card.tap()
        let edit = app.buttons["lio.memory.edit"]
        XCTAssertTrue(edit.waitForExistence(timeout: 10))
        edit.tap()
        let editor = app.descendants(matching: .any).matching(identifier: "lio.memory.editor").firstMatch
        XCTAssertTrue(editor.waitForExistence(timeout: 5))
        editor.tap()
        editor.typeText(" Near a station.")
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(keyboard.exists)
        app.navigationBars.buttons["lio.memory.keyboard-done"].tap()
        let dismissed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: keyboard)
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
        XCTAssertTrue((editor.value as? String)?.contains("Near a station.") == true)
        XCTAssertTrue(app.buttons["lio.memory.save"].isEnabled)
    }

    func testConfirmingEachPreferenceRefreshesItsSiblingAndTheMemoryGridInBothLanguages() throws {
        continueAfterFailure = false
        for (chinese, appearance) in [(false, "light"), (true, "light"), (false, "dark"), (true, "dark")] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.memory-siblings.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-memory-titled-acceptance", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                   "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
            app.launch()
            defer { app.terminate() }
            let choices = app.buttons.matching(identifier: "lio.memory.remember")
            let two = XCTNSPredicateExpectation(predicate: NSPredicate(format: "count == 2"), object: choices)
            XCTAssertEqual(XCTWaiter.wait(for: [two], timeout: 10), .completed)
            let memory = app.tabBars.buttons[chinese ? "记忆" : "Memory"]
            let chat = app.tabBars.buttons[chinese ? "聊天" : "Chat"]
            let hotel = app.buttons["lio.memory.card.luxury-hotel"]
            let museum = app.buttons["lio.memory.card.museum"]
            let suggestions = app.staticTexts["lio.memory.suggestions"]
            let firstSuggestion = app.staticTexts["lio.memory.suggestion.0"]
            let secondSuggestion = app.staticTexts["lio.memory.suggestion.1"]
            memory.tap()
            XCTAssertTrue(suggestions.waitForExistence(timeout: 8))
            XCTAssertEqual(firstSuggestion.label, chinese ? "你偏好豪华酒店。" : "You prefer luxury hotels.")
            XCTAssertEqual(secondSuggestion.label, chinese ? "你喜欢参观博物馆。" : "You enjoy museums.")
            XCTAssertTrue(app.staticTexts[chinese ? "你让 Lio 记住的内容会出现在这里。" : "Things you ask Lio to remember appear here."].waitForExistence(timeout: 10))
            XCTAssertFalse(hotel.exists); XCTAssertFalse(museum.exists)
            try app.performAccessibilityAudit(for: .all)
            chat.tap()
            choices.element(boundBy: 0).tap()
            let one = XCTNSPredicateExpectation(predicate: NSPredicate(format: "count == 1"), object: choices)
            XCTAssertEqual(XCTWaiter.wait(for: [one], timeout: 10), .completed)
            memory.tap()
            XCTAssertTrue(hotel.waitForExistence(timeout: 10))
            XCTAssertEqual(hotel.value as? String, chinese ? "你偏好豪华酒店。" : "You prefer luxury hotels.")
            XCTAssertFalse(museum.exists, "The unconfirmed sibling must not be saved")
            XCTAssertEqual(firstSuggestion.label, chinese ? "你喜欢参观博物馆。" : "You enjoy museums.")
            XCTAssertFalse(secondSuggestion.exists)
            chat.tap()
            XCTAssertTrue(choices.firstMatch.waitForExistence(timeout: 10))
            choices.firstMatch.tap()
            let none = XCTNSPredicateExpectation(predicate: NSPredicate(format: "count == 0"), object: choices)
            XCTAssertEqual(XCTWaiter.wait(for: [none], timeout: 10), .completed)
            memory.tap()
            XCTAssertFalse(suggestions.exists)
            XCTAssertTrue(hotel.waitForExistence(timeout: 10))
            XCTAssertTrue(museum.waitForExistence(timeout: 10))
            XCTAssertEqual(museum.value as? String, chinese ? "你喜欢参观博物馆。" : "You enjoy museums.")
            XCTAssertEqual(hotel.frame.width, museum.frame.width, accuracy: 0.5)
            XCTAssertEqual(hotel.frame.height, museum.frame.height, accuracy: 0.5)
            app.buttons["fixture.siblings.inspect"].tap()
            XCTAssertEqual(app.staticTexts["fixture.siblings.state"].label, "saved=2|actions=2|stale=0|refreshed=true")
            try app.performAccessibilityAudit(for: .all)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "two-confirmed-preferences-\(appearance)-\(chinese ? "zh" : "en")"; image.lifetime = .keepAlways; add(image)
        }
    }
}
