import XCTest

@MainActor final class LioPagedHistoryUITests: XCTestCase {
    func testLoadedHistoryCountAndMessageOrderAreAccessibleInBothLanguages() throws {
        try exerciseInitial(appearance: "light")
    }
    func testDarkLoadedHistoryCountAndMessageOrderAreAccessibleInBothLanguages() throws {
        try exerciseInitial(appearance: "dark")
    }
    private func exerciseInitial(appearance: String) throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            print("HISTORY_AUDIT_LANGUAGE_\(chinese ? "ZH" : "EN")")
            let app = XCUIApplication(bundleIdentifier: "space.go2china.paged-history.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                   "-lio.ui.appearance.v1", appearance]
            app.launch()
            let position = app.staticTexts["lio.position.19.loaded.20.earlier.1"]
            XCTAssertTrue(position.waitForExistence(timeout: 8))
            XCTAssertEqual(position.label, "Lio")
            let answer = app.staticTexts["lio.answer"].firstMatch
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", chinese ? "回复已完成" : "Reply complete"), object: answer)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 8), .completed)
            XCTAssertTrue(app.textViews.matching(identifier: "lio.question").firstMatch.exists)
            waitForVisibleRepliesToSettle(app, chinese: chinese)
            try app.performAccessibilityAudit(for: .all) { issue in
                let detail = XCTAttachment(string: issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No element") + "\n" + app.debugDescription)
                detail.name = "history-complete-audit"; detail.lifetime = .keepAlways; self.add(detail)
                return false
            }
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "history-order-\(chinese ? "zh" : "en")-\(appearance)"; image.lifetime = .keepAlways; add(image)
            app.terminate()
        }
    }
    private struct VisibleReply: Equatable {
        let frame: CGRect
        let label: String
        let value: String
    }
    private func waitForVisibleRepliesToSettle(_ app: XCUIApplication, chinese: Bool) {
        var previous: [VisibleReply]?
        let ready = NSPredicate { _, _ in
            guard let root = try? app.snapshot() else { return false }
            let bounds = app.frame
            var replies: [VisibleReply] = []
            func visit(_ node: any XCUIElementSnapshot) {
                if node.identifier == "lio.answer", !node.frame.isEmpty, bounds.intersects(node.frame) {
                    replies.append(VisibleReply(frame: node.frame, label: node.label, value: node.value as? String ?? ""))
                }
                node.children.forEach(visit)
            }
            visit(root)
            guard !replies.isEmpty, replies.allSatisfy({ $0.value == (chinese ? "回复已完成" : "Reply complete") }) else {
                previous = nil
                return false
            }
            let settled = previous == replies
            previous = replies
            return settled
        }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: ready, object: nil)], timeout: 8), .completed)
    }

}


extension LioPagedHistoryUITests {
    private struct Node {
        let identifier: String
        let label: String
        let value: String
        let frame: CGRect
        let depth: Int
    }
    private struct Row: Equatable {
        let question: String
        let answer: String?
        let failure: String?
    }

    func testCompleteNativeEnglishHistoryPreservesRepeatedRowsAndHistoricalFailure() throws {
        try exerciseComplete(chinese: false)
    }
    func testCompleteNativeChineseHistoryPreservesRepeatedRows() throws {
        try exerciseComplete(chinese: true)
    }
    private func exerciseComplete(chinese: Bool) throws {
        continueAfterFailure = false
            let app = XCUIApplication(bundleIdentifier: "space.go2china.paged-history.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                   "-lio.ui.appearance.v1", "light"]
            app.launch()
            defer { app.terminate() }
            XCTAssertTrue(app.staticTexts["lio.position.19.loaded.20.earlier.1"].waitForExistence(timeout: 8))
            let scroll = app.scrollViews.firstMatch
            let earlier = app.buttons["lio.earlier"]
            let total = chinese ? 32 : 41
            var count = 20
            var page = 0
            // Use the actual load-earlier control, not the fixture's page function.
            while count < total {
                var reached = false
                for _ in 0..<20 {
                    if earlier.exists && earlier.isHittable && earlier.frame.minY > 130 {
                        reached = true; break
                    }
                    scroll.swipeDown(velocity: .fast)
                }
                XCTAssertTrue(reached, "The existing earlier-page control must be reachable")
                earlier.tap()
                count = min(count + 20, total)
                let marker = app.staticTexts["lio.position.0.loaded.\(count).earlier.\(count == total ? 0 : 1)"]
                XCTAssertTrue(marker.waitForExistence(timeout: 8))
                page += 1
            }
            XCTAssertEqual(page, chinese ? 1 : 2)
            XCTAssertFalse(earlier.exists)
            var observed: [Int: Row] = [:]
            for slice in 0..<60 {
                let root = try app.snapshot()
                var nodes: [Node] = []
                func flatten(_ item: any XCUIElementSnapshot, depth: Int = 0) {
                    let identifier = item.identifier
                    if identifier.hasPrefix("lio.") {
                        nodes.append(Node(identifier: identifier, label: item.label,
                                          value: item.value as? String ?? "", frame: item.frame, depth: depth))
                    }
                    if !["lio.question", "lio.answer", "lio.opening", "lio.composer"].contains(identifier) {
                        item.children.forEach { flatten($0, depth: depth + 1) }
                    }
                }
                flatten(root)
                let original: [[String: Any]] = nodes.map { ["identifier": $0.identifier, "label": $0.label, "value": $0.value, "depth": $0.depth, "frame": [$0.frame.minX, $0.frame.minY, $0.frame.width, $0.frame.height]] }
                let attachment = XCTAttachment(data: try JSONSerialization.data(withJSONObject: original), uniformTypeIdentifier: "public.json")
                attachment.name = "native-page-\(chinese ? "zh" : "en")-\(slice)"
                attachment.lifetime = .keepAlways; add(attachment)
                XCTAssertFalse(nodes.contains { $0.label.contains("A hidden historical partial answer") })
                let questions = nodes.indices.filter { nodes[$0].identifier == "lio.question" }
                for (offset, start) in questions.enumerated() {
                    let end = offset + 1 < questions.count ? questions[offset + 1] : nodes.count
                    let children = Array(nodes[start..<end])
                    let positions = children.filter { $0.identifier.hasPrefix("lio.position.") }
                    guard positions.count == 1 else { continue }
                    let parts = positions[0].identifier.split(separator: ".")
                    guard parts.count == 7, let ordinal = Int(parts[2]), Int(parts[4]) == total,
                          parts[6] == "0" else { continue }
                    let answers = children.filter { $0.identifier == "lio.answer" }
                    let failures = children.filter { $0.identifier == "lio.failure" }
                    let row: Row
                    if answers.count == 1 && failures.isEmpty && answers[0].value == (chinese ? "回复已完成" : "Reply complete") {
                        row = Row(question: nodes[start].value, answer: answers[0].label, failure: nil)
                    } else if failures.count == 1 && answers.isEmpty {
                        row = Row(question: nodes[start].value, answer: nil, failure: failures[0].label)
                    } else { continue }
                    if let previous = observed[ordinal] { XCTAssertEqual(previous, row) }
                    observed[ordinal] = row
                }
                if observed.count == total { break }
                scroll.swipeUp(velocity: .slow)
            }
            XCTAssertEqual(observed.count, total)
            for ordinal in 0..<total {
                let row = try XCTUnwrap(observed[ordinal])
                XCTAssertEqual(row.question, "Synthetic question " + String(ordinal % 3))
                if !chinese && ordinal == 5 {
                    XCTAssertNil(row.answer)
                    XCTAssertEqual(row.failure, "I couldn’t complete this request.")
                } else {
                    XCTAssertNil(row.failure)
                    XCTAssertEqual(row.answer, "Synthetic answer " + String(ordinal % 2))
                }
            }
            let jump = app.buttons["lio.jumpToLatest"]
            XCTAssertTrue(jump.isHittable)
            let jumpFrame = jump.frame
            for body in app.staticTexts.matching(identifier: "lio.answer").allElementsBoundByIndex {
                let frame = body.frame
                if !frame.isEmpty { XCTAssertFalse(frame.intersects(jumpFrame), "Jump must not cover a reply body") }
            }
            waitForVisibleRepliesToSettle(app, chinese: chinese)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "settled-full-history-\(chinese ? "zh" : "en")"; image.lifetime = .keepAlways; add(image)
            try app.performAccessibilityAudit(for: .all) { issue in
                let detail = XCTAttachment(string: issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No element") + "\n" + app.debugDescription)
                detail.name = "history-full-audit"; detail.lifetime = .keepAlways; self.add(detail)
                return false
            }
            app.terminate()
    }
}
