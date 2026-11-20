import XCTest

@MainActor final class LioTabBarUITests: XCTestCase {
    func testFourTabsAppearInOrderAndToolsStaysSelectedOnReturn() throws {
        continueAfterFailure = false
        for (language, labels) in [("en", ["Chat", "Trips", "Tools", "Memory"]),
                                  ("zh-Hans", ["聊天", "行程", "插件", "记忆"])] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.tab.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tab-order-acceptance", "-cj.ui.language.v1", language]
            app.launch()
            defer { app.terminate() }
            let tabs = labels.map { app.tabBars.buttons[$0] }
            XCTAssertTrue(tabs[0].waitForExistence(timeout: 10))
            XCTAssertEqual(app.tabBars.buttons.count, 4)
            for pair in zip(tabs, tabs.dropFirst()) {
                XCTAssertLessThan(pair.0.frame.midX, pair.1.frame.midX)
            }
            XCTAssertTrue(tabs[0].isSelected)
            try audit(app, name: "four-tabs-\(language)")
            tabs[2].tap()
            XCTAssertTrue(app.buttons["lio.tools.translation"].waitForExistence(timeout: 5))
            XCUIDevice.shared.press(.home)
            app.activate()
            XCTAssertTrue(tabs[2].isSelected)
            let tripsAvailable = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in tabs[1].isHittable }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [tripsAvailable], timeout: 8), .completed)
            tabs[1].tap()
            XCTAssertTrue(tabs[1].isSelected)
            tabs[3].tap()
            XCTAssertTrue(tabs[3].isSelected)
            tabs[0].tap()
            XCTAssertTrue(tabs[0].isSelected)
        }
    }
    func testEnglishLightHomeAndHistoryTabs() throws { try exercise(chinese: false, appearance: "light") }
    func testChineseLightHomeAndHistoryTabs() throws { try exercise(chinese: true, appearance: "light") }
    func testEnglishDarkHomeAndHistoryTabs() throws { try exercise(chinese: false, appearance: "dark") }
    func testChineseDarkHomeAndHistoryTabs() throws { try exercise(chinese: true, appearance: "dark") }

    private func exercise(chinese: Bool, appearance: String) throws {
        continueAfterFailure = false
        for history in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.tab.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                   "-lio.ui.appearance.v1", appearance,
                                   "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
            if history { app.launchArguments.append("--lio-tab-history-acceptance") }
            app.launch()
            defer { app.terminate() }
            let chat = app.tabBars.buttons[chinese ? "聊天" : "Chat"]
            let trips = app.tabBars.buttons[chinese ? "行程" : "Trips"]
            XCTAssertTrue(chat.waitForExistence(timeout: 12))
            XCTAssertTrue(chat.isSelected)
            XCTAssertTrue(trips.isEnabled)
            XCTAssertFalse(trips.isSelected)
            if history {
                let body = app.staticTexts["An earlier reply."]
                XCTAssertTrue(body.waitForExistence(timeout: 8))
                let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", chinese ? "回复已完成" : "Reply complete"), object: body)
                XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 8), .completed)
            } else {
                XCTAssertTrue(app.staticTexts["lio.opening"].waitForExistence(timeout: 8))
            }
            try audit(app, name: history ? "history-chat-initial" : "ordinary-home")
            trips.tap()
            XCTAssertTrue(trips.isSelected)
            XCTAssertFalse(chat.isSelected)
            XCTAssertTrue(chat.isEnabled)
            try audit(app, name: "trips-selected")
            chat.tap()
            XCTAssertTrue(chat.isSelected)
            XCTAssertFalse(trips.isSelected)
            if history {
                app.buttons["lio.menu"].tap()
                let entry = app.buttons["lio.chat.history"]
                XCTAssertTrue(entry.waitForExistence(timeout: 8))
                entry.tap()
                XCTAssertTrue(app.navigationBars[chinese ? "历史对话" : "Chat history"].waitForExistence(timeout: 8))
                let row = app.buttons["lio.chat.history.row"].firstMatch
                let empty = app.staticTexts[chinese ? "你的对话会出现在这里。" : "Your conversations will appear here."]
                let loaded = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in row.exists || empty.exists }, object: nil)
                XCTAssertEqual(XCTWaiter.wait(for: [loaded], timeout: 8), .completed)
                XCTAssertFalse(app.staticTexts[chinese ? "暂时看不到对话。" : "Couldn’t show your conversations."].exists)
                try audit(app, name: "existing-chat-history-entry")
            } else {
                try audit(app, name: "ordinary-home-return")
            }
            app.terminate()
        }
    }

    private func audit(_ app: XCUIApplication, name: String) throws {
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = name; screenshot.lifetime = .keepAlways; add(screenshot)
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No element") + "\n" + app.debugDescription)
            detail.name = name + "-all-issue"; detail.lifetime = .keepAlways; self.add(detail)
            return false
        }
    }
}
