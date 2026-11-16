import XCTest

@MainActor final class LioReplyStateUITests: XCTestCase {
    func testReplyingAndCompleteValuesKeepTheOriginalBodyInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
          for appearance in ["light", "dark"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.reply-state.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", appearance]
            app.launch()
            let begin = app.buttons["fixture.reply.begin"]
            XCTAssertTrue(begin.waitForExistence(timeout: 8))
            begin.tap()
            let answer = app.staticTexts["lio.answer"]
            XCTAssertTrue(answer.waitForExistence(timeout: 5))
            let replying = chinese ? "正在回复…" : "Replying…"
            XCTAssertEqual(answer.value as? String, replying)
            app.buttons["fixture.reply.finish"].tap()
            let complete = chinese ? "回复已完成" : "Reply complete"
            let done = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", complete), object: answer)
            XCTAssertEqual(XCTWaiter.wait(for: [done], timeout: 8), .completed)
            XCTAssertEqual(answer.label, chinese ? "第一条回答。完整回答已经显示。" : "First reply. All of the reply is here.")
            try app.performAccessibilityAudit(for: .all)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "reply-state-\(chinese ? "zh" : "en")-\(appearance)"; image.lifetime = .keepAlways; add(image)
            app.buttons["fixture.reply.reject"].tap()
            XCTAssertTrue(app.staticTexts["lio.reply.unavailable"].waitForExistence(timeout: 5))
            XCTAssertFalse(answer.exists)
            app.terminate()
          }
        }
    }
}
