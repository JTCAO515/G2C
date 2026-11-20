import XCTest

@MainActor extension LioToolsUITests {
    @objc func testTranslationKeyboardDismissesWithoutMovingThePageControls() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        let tools = app.tabBars.buttons["Tools"]
        XCTAssertTrue(tools.waitForExistence(timeout: 8))
        tools.tap()
        app.buttons["lio.tools.translation"].tap()
        let editor = app.textViews["lio.translation.input"]
        XCTAssertTrue(editor.waitForExistence(timeout: 6))
        let translate = app.buttons["lio.translation.submit"]
        let initialFrame = translate.frame
        let keyboard = app.keyboards.firstMatch
        let done = app.navigationBars.buttons["lio.translation.keyboard-done"]

        func capture(_ name: String) {
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = name
            shot.lifetime = .keepAlways
            add(shot)
        }
        func expectDismissed() {
            let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: keyboard)
            XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 5), .completed)
            XCTAssertFalse(done.exists)
            XCTAssertEqual(translate.frame.origin.x, initialFrame.origin.x, accuracy: 1)
            XCTAssertEqual(translate.frame.origin.y, initialFrame.origin.y, accuracy: 1)
        }

        capture("translation-before-editing")
        editor.tap()
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        editor.typeText("Keep this draft")
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        capture("translation-keyboard-and-done")
        done.tap()
        expectDismissed()
        XCTAssertEqual(editor.value as? String, "Keep this draft")
        capture("translation-after-done")

        editor.tap()
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        editor.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0.25))
            .withOffset(CGVector(dx: -8, dy: 0)).tap()
        expectDismissed()

        editor.tap()
        XCTAssertTrue(keyboard.waitForExistence(timeout: 5))
        let scroller = app.scrollViews["lio.translation.scroll"]
        XCTAssertTrue(scroller.exists)
        let belowEditor = editor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 1))
            .withOffset(CGVector(dx: 0, dy: 5))
        let aboveEditor = editor.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0))
            .withOffset(CGVector(dx: 0, dy: -5))
        belowEditor.press(forDuration: 0.05, thenDragTo: aboveEditor)
        expectDismissed()
        XCTAssertEqual(editor.value as? String, "Keep this draft")
    }
}
