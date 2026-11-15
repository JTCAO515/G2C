import XCTest

@MainActor final class LioVoiceOverUITests: XCTestCase {
    enum WalkFailure: Error { case notHeard(String) }

    func testBilingualExplorationInteractionsWithActualVoiceOver() throws {
        guard #available(iOS 27.0, *) else { XCTFail("This dedicated VoiceOver engine acceptance requires iOS 27."); return }
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        let voice = XCUIDevice.shared.voiceOverService
        let wasEnabled = voice.isEnabled
        var transcript: [String] = []
        addTeardownBlock {
            try await MainActor.run {
                let service = XCUIDevice.shared.voiceOverService
                if service.isEnabled != wasEnabled {
                    if wasEnabled { try service.enable() } else { try service.disable() }
                }
                XCTAssertEqual(service.isEnabled, wasEnabled)
                print("OWNED_VOICEOVER_RESTORED", service.isEnabled)
                XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance").terminate()
            }
        }
        defer {
            let evidence = XCTAttachment(string: transcript.joined(separator: "\n"))
            evidence.name = "Actual VoiceOver interaction utterances, synthetic only"
            evidence.lifetime = .keepAlways; add(evidence)
        }
        func log(_ text: String) {
            transcript.append(text)
            print("ACTUAL_VOICEOVER", text)
        }
        func hear(_ text: String) throws {
            for _ in 0..<80 {
                let spoken = try voice.moveForward().utterance
                log(spoken)
                if spoken.contains(text) { return }
            }
            throw WalkFailure.notHeard(text)
        }
        func activate(_ element: XCUIElement, spokenLabel: String) throws {
            let ready = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in
                element.exists && element.isEnabled && element.isHittable
            }, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 12), .completed)
            element.tap()
            let spoken = try voice.currentSpeech().utterance
            log("Focus: " + spoken)
            XCTAssertTrue(spoken.contains(spokenLabel), transcript.joined(separator: "\n"))
            element.doubleTap()
        }
        for chinese in [false, true] {
            if voice.isEnabled { try voice.disable() }
            let language = chinese ? "zh-Hans" : "en"
            app.launchArguments = ["--lio-preview", "--lio-exploration-home-acceptance", "-cj.ui.language.v1", language,
                                   "-lio.ui.appearance.v1", "light"]
            app.launch()
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(composer.waitForExistence(timeout: 12))
            composer.tap(); composer.typeText("I would like some travel ideas")
            app.buttons["lio.send"].tap()
            XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "lio.segment.0").firstMatch.waitForExistence(timeout: 12))
            try voice.enable(); XCTAssertTrue(voice.isEnabled)
            log("--- " + language + " ---")
            app.buttons["lio.menu"].tap()
            log(try voice.currentSpeech().utterance)
            try hear(chinese ? "可以先聊一个大致安排" : "We can start with an outline")
            try hear(chinese ? "日期可以之后再定" : "Dates can stay open for now")
            try hear(chinese ? "历史" : "History")
            let history = app.buttons.matching(NSPredicate(format: "identifier ENDSWITH %@", ".interests.history")).firstMatch
            try activate(history, spokenLabel: chinese ? "历史" : "History")
            XCTAssertTrue(history.isSelected)
            try hear(chinese ? "自然" : "Nature")
            let nature = app.buttons.matching(NSPredicate(format: "identifier ENDSWITH %@", ".interests.nature")).firstMatch
            try activate(nature, spokenLabel: chinese ? "自然" : "Nature")
            XCTAssertTrue(nature.isSelected)
            try hear(chinese ? "Lio 注意到" : "Lio noticed")
            try hear(chinese ? "带一件雨衣" : "Bring a raincoat")
            try hear(chinese ? "来源" : "Source")
            try activate(app.buttons["lio.questions.continue"], spokenLabel: chinese ? "好了，继续" : "Done, continue")
            let joint = chinese ? "兴趣：历史\n兴趣：自然" : "Interests: History\nInterests: Nature"
            let jointQuestions = app.staticTexts.matching(identifier: "lio.question").matching(NSPredicate(format: "label == %@", joint))
            XCTAssertTrue(jointQuestions.firstMatch.waitForExistence(timeout: 12))
            XCTAssertEqual(jointQuestions.count, 1)

            func readCount(_ expected: Int) throws -> String {
                try activate(app.buttons["lio.menu"], spokenLabel: chinese ? "菜单" : "Menu")
                let count = app.staticTexts["fixture.send-count"]
                XCTAssertTrue(count.waitForExistence(timeout: 8))
                let exact = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", String(expected)), object: count)
                XCTAssertEqual(XCTWaiter.wait(for: [exact], timeout: 8), .completed)
                let id = try XCTUnwrap(count.value as? String)
                XCTAssertFalse(id.isEmpty)
                try activate(app.buttons[chinese ? "完成" : "Done"], spokenLabel: chinese ? "完成" : "Done")
                XCTAssertTrue(count.waitForNonExistence(timeout: 8))
                return id
            }
            let secondID = try readCount(2)
            let secondReply = app.descendants(matching: .any).matching(identifier: "lio.exploration." + secondID).firstMatch
            let profile = secondReply.buttons["lio.profile.pace"]
            try activate(profile, spokenLabel: chinese ? "慢慢逛" : "An easy pace")
            let field = app.descendants(matching: .any).matching(identifier: "lio.profile.edit.text").firstMatch
            XCTAssertTrue(field.waitForExistence(timeout: 8))
            field.tap(); field.doubleTap()
            let original = try XCTUnwrap(field.value as? String)
            let change = chinese ? "节奏改为轻松" : "Prefer a relaxed pace"
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: original.count) + change)
            XCTAssertEqual(field.value as? String, change)
            try activate(app.buttons["lio.profile.edit.send"], spokenLabel: chinese ? "发送" : "Send")
            XCTAssertTrue(field.waitForNonExistence(timeout: 8))
            let editedQuestions = app.staticTexts.matching(identifier: "lio.question").matching(NSPredicate(format: "label == %@", change))
            XCTAssertTrue(editedQuestions.firstMatch.waitForExistence(timeout: 12))
            XCTAssertEqual(editedQuestions.count, 1)
            let thirdID = try readCount(3)
            let thirdReply = app.descendants(matching: .any).matching(identifier: "lio.exploration." + thirdID).firstMatch
            try activate(thirdReply.buttons["lio.exit.plan_now"], spokenLabel: chinese ? "直接出方案" : "Make a plan now")
            _ = try readCount(4)
            try activate(composer, spokenLabel: chinese ? "开始聊天" : "Start chatting")
            let followUp = chinese ? "还可以聊些什么？" : "What can we discuss next?"
            composer.typeText(followUp)
            try activate(app.buttons["lio.send"], spokenLabel: chinese ? "发送" : "Send")
            let followUpQuestions = app.staticTexts.matching(identifier: "lio.question").matching(NSPredicate(format: "label == %@", followUp))
            XCTAssertTrue(followUpQuestions.firstMatch.waitForExistence(timeout: 12))
            XCTAssertEqual(followUpQuestions.count, 1)
            _ = try readCount(5)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "VoiceOver-interactions-" + language; image.lifetime = .keepAlways; add(image)
            try voice.disable(); XCTAssertFalse(voice.isEnabled)
            app.terminate()
        }
    }
}
