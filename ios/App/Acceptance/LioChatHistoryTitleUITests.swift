import XCTest

@MainActor final class LioChatHistoryTitleUITests: XCTestCase {
    func testEnglishLightHistoryTitleAndReturn() throws { try exercise(chinese: false, appearance: "light") }
    func testChineseLightHistoryTitleAndReturn() throws { try exercise(chinese: true, appearance: "light") }
    func testEnglishDarkHistoryTitleAndReturn() throws { try exercise(chinese: false, appearance: "dark") }
    func testChineseDarkHistoryTitleAndReturn() throws { try exercise(chinese: true, appearance: "dark") }

    private func exercise(chinese: Bool, appearance: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.history.title.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                               "-lio.ui.appearance.v1", appearance,
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch()
        defer { app.terminate() }
        let body = app.staticTexts["An earlier reply."]
        XCTAssertTrue(body.waitForExistence(timeout: 12))
        let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", chinese ? "回复已完成" : "Reply complete"), object: body)
        XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 8), .completed)
        let chat = app.tabBars.buttons[chinese ? "聊天" : "Chat"]
        let trips = app.tabBars.buttons[chinese ? "行程" : "Trips"]
        XCTAssertTrue(chat.isSelected)
        try audit(app, name: "original-home")
        trips.tap()
        XCTAssertTrue(trips.isSelected)
        try audit(app, name: "trips-selected")
        chat.tap()
        XCTAssertTrue(chat.isSelected)
        for visit in 1...2 {
            app.buttons["lio.menu"].tap()
            let history = app.buttons["lio.chat.history"]
            XCTAssertTrue(history.waitForExistence(timeout: 8))
            history.tap()
            let title = chinese ? "历史对话" : "Chat history"
            let navigation = app.navigationBars[title]
            XCTAssertTrue(navigation.waitForExistence(timeout: 8))
            try assertOneSemanticTitle(navigation, title: title)
            let row = app.buttons["lio.chat.history.row"].firstMatch
            let empty = app.staticTexts[chinese ? "你的对话会出现在这里。" : "Your conversations will appear here."]
            let loaded = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in row.exists || empty.exists }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [loaded], timeout: 8), .completed)
            XCTAssertFalse(app.staticTexts[chinese ? "暂时看不到对话。" : "Couldn’t show your conversations."].exists)
            try audit(app, name: "history-title-visit-\(visit)")
            let back = navigation.buttons.firstMatch
            XCTAssertTrue(back.isHittable)
            back.tap()
            XCTAssertTrue(history.waitForExistence(timeout: 8))
            let done = app.buttons[chinese ? "完成" : "Done"]
            XCTAssertTrue(done.isHittable)
            done.tap()
            XCTAssertTrue(chat.isSelected)
            XCTAssertTrue(body.waitForExistence(timeout: 8))
            XCTAssertEqual(body.label, "An earlier reply.")
        }
    }

    private func assertOneSemanticTitle(_ navigation: XCUIElement, title: String) throws {
        let root = try navigation.snapshot()
        var titles: [any XCUIElementSnapshot] = []
        func visit(_ node: any XCUIElementSnapshot) {
            if node.elementType == .staticText, node.label == title {
                titles.append(node)
                return // A labeled parent and its nested text describe one semantic title.
            }
            node.children.forEach(visit)
        }
        visit(root)
        let rawCount = navigation.staticTexts.matching(NSPredicate(format: "label == %@", title)).count
        let tree = XCTAttachment(string: "raw title nodes: \(rawCount)\nsemantic titles: \(titles.count)\n" + navigation.debugDescription)
        tree.name = "history-title-original-hierarchy"; tree.lifetime = .keepAlways; add(tree)
        XCTAssertEqual(titles.count, 1, navigation.debugDescription)
        XCTAssertEqual(titles.first?.label, title)
    }

    private func audit(_ app: XCUIApplication, name: String) throws {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No element") + "\n" + app.debugDescription)
            detail.name = name + "-all-issue"; detail.lifetime = .keepAlways; self.add(detail)
            return false
        }
    }
}
