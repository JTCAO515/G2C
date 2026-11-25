import XCTest
import UIKit
import CryptoKit

@MainActor final class LioToolsUITests: XCTestCase {
    func testPaymentGuideShowsSetupAndTroubleshootingInBothLanguages() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                       "UICTContentSizeCategoryL"]
                app.launch()
                defer { app.terminate() }
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "工具"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                app.buttons["lio.tools.payment-guide"].tap()
                for provider in ["alipay", "weixin"] {
                    app.buttons["lio.payment.provider." + provider].tap()
                    XCTAssertTrue(app.descendants(matching: .any)["lio.payment.official"].exists)
                    try app.performAccessibilityAudit(for: .all)
                    for step in ["register", "find-card", "add-card", "verify"] {
                        let row = app.buttons["lio.payment.open-step." + step]
                        XCTAssertTrue(row.exists)
                        row.tap()
                        XCTAssertTrue(app.staticTexts["lio.payment.step." + step].exists)
                        try app.performAccessibilityAudit(for: .all)
                        app.navigationBars.firstMatch.buttons.firstMatch.tap()
                    }
                    let screenshot = XCTAttachment(screenshot: app.screenshot())
                    screenshot.name = "payment-\(provider)-\(language)-\(appearance)"
                    screenshot.lifetime = .keepAlways
                    add(screenshot)
                    let problems = app.buttons["lio.payment.problems"]
                    for _ in 0..<4 where !problems.isHittable { app.swipeUp() }
                    XCTAssertTrue(problems.isHittable)
                    problems.tap()
                    XCTAssertTrue(app.staticTexts["lio.payment.step.issuer"].waitForExistence(timeout: 6))
                    try app.performAccessibilityAudit(for: .all)
                    app.navigationBars.firstMatch.buttons.firstMatch.tap()
                    app.navigationBars.firstMatch.buttons.firstMatch.tap()
                }
            }
        }
    }

    /// #1450 item 2: the interactive map opens from a city, finds a station and shows its lines,
    /// the taxi and directions actions, and the operator source with its check date.
    func testMetroMapFindsAStationAndShowsItsLines() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-tools-preview", "--lio-taxi-preview", "-cj.ui.language.v1", language,
                                   "-lio.ui.appearance.v1", "light", "-UIPreferredContentSizeCategoryName",
                                   "UICTContentSizeCategoryL"]
            app.launch()
            defer { app.terminate() }
            let english = language == "en"
            let tools = app.tabBars.buttons[english ? "Tools" : "工具"]
            XCTAssertTrue(tools.waitForExistence(timeout: 8))
            tools.tap()
            app.buttons["lio.tools.metro-guide"].tap()
            for (city, station, lines) in [("guangzhou", english ? "Tiyu Xilu" : "体育西路", english ? "Line 1" : "1号线"),
                                           ("shanghai", english ? "People's Square" : "人民广场", english ? "Line 8" : "8号线"),
                                           ("beijing", english ? "Xizhimen" : "西直门", english ? "Line 13" : "13号线")] {
                XCTAssertTrue(app.buttons["lio.metro.city.\(city)"].waitForExistence(timeout: 6))
                app.buttons["lio.metro.city.\(city)"].tap() // a city opens straight into its map
                XCTAssertTrue(app.descendants(matching: .any)["lio.metro.map.canvas"].waitForExistence(timeout: 8))
                let source = app.descendants(matching: .any)["lio.metro.map.source"]
                XCTAssertTrue(source.exists)
                XCTAssertTrue(source.label.contains(english ? "checked 24 Nov 2026" : "核对于2026年11月24日"))
                capture(app, "metro-map-\(city)-\(language)")
                app.buttons["lio.metro.map.zoom-in"].tap()
                app.buttons["lio.metro.map.zoom-in"].tap()
                capture(app, "metro-map-\(city)-zoomed-\(language)")
                app.buttons["lio.metro.map.find"].tap()
                let search = app.searchFields.firstMatch
                XCTAssertTrue(search.waitForExistence(timeout: 6))
                search.tap()
                search.typeText(station)
                let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", station)).firstMatch
                XCTAssertTrue(row.waitForExistence(timeout: 6))
                row.tap()
                XCTAssertTrue(app.staticTexts["lio.metro.station.name-zh"].waitForExistence(timeout: 6))
                XCTAssertTrue(app.descendants(matching: .any)["lio.metro.station.lines"].label.contains(lines))
                XCTAssertTrue(app.staticTexts["lio.metro.station.interchange"].exists)
                XCTAssertTrue(app.buttons["lio.metro.station.taxi"].exists)
                XCTAssertTrue(app.buttons["lio.metro.station.directions"].exists)
                capture(app, "metro-station-\(city)-\(language)")
                if city == "guangzhou" {
                    // The preview place search has no metro stations, so this proves the query it sent:
                    // the app's own taxi search for "<station>地铁站" in the station's city.
                    app.buttons["lio.metro.station.taxi"].tap()
                    let notice = app.staticTexts["lio.metro.station.notice"]
                    XCTAssertTrue(notice.waitForExistence(timeout: 8))
                    XCTAssertTrue(notice.label.contains("体育西路地铁站"))
                    capture(app, "metro-taxi-search-\(city)-\(language)")
                }
                app.swipeDown(velocity: .fast)
                XCTAssertTrue(app.descendants(matching: .any)["lio.metro.map.canvas"].waitForExistence(timeout: 6))
                app.navigationBars.buttons.element(boundBy: 0).tap() // back to the city list
            }
        }
    }

    private func capture(_ app: XCUIApplication, _ name: String) {
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = name
        screenshot.lifetime = .keepAlways
        add(screenshot)
    }

    func testMetroCitiesOpenTheirMaps() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                       "UICTContentSizeCategoryL"]
                app.launch()
                defer { app.terminate() }
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "工具"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                app.buttons["lio.tools.metro-guide"].tap()
                // Choose a city first (#1421); its map opens next.
                for city in ["beijing", "shanghai", "guangzhou", "shenzhen"] {
                    XCTAssertTrue(app.buttons["lio.metro.city.\(city)"].waitForExistence(timeout: 6))
                }
                // The city list runs on under the translucent tab bar, where contrast is measured through the bar
                // rather than on the card. Only that case is set aside: contrast issues are collected during the
                // audit (reading an element's frame inside the handler breaks the audit) and each must then lie
                // under the tab bar. Every other audit runs.
                let tabBar = app.tabBars.firstMatch
                XCTAssertTrue(tabBar.exists)
                let tabBarTop = tabBar.frame.minY
                var underTabBar: [XCUIElement] = []
                try app.performAccessibilityAudit(for: .all) { issue in
                    guard issue.auditType == .contrast, let element = issue.element else { return false }
                    underTabBar.append(element)
                    return true
                }
                for element in underTabBar {
                    XCTAssertGreaterThan(element.frame.maxY, tabBarTop, "contrast issue above the tab bar: \(element)")
                }
                let cities = XCTAttachment(screenshot: app.screenshot())
                cities.name = "metro-cities-\(language)-\(appearance)"
                cities.lifetime = .keepAlways
                add(cities)
                // A city card opens its map directly: no ticket or security steps (JT 2026-11-25).
                app.buttons["lio.metro.city.shanghai"].tap()
                let canvas = app.descendants(matching: .any)["lio.metro.map.canvas"]
                XCTAssertTrue(canvas.waitForExistence(timeout: 8))
                XCTAssertFalse(app.staticTexts["lio.metro.ticket"].exists)
                app.navigationBars.buttons.element(boundBy: 0).tap()
                // "Find a city" lists every city in the same order, searchable, and opens the chosen map.
                let find = app.buttons["lio.metro.city.find"]
                XCTAssertTrue(find.waitForExistence(timeout: 6))
                find.tap()
                let xian = app.buttons["lio.metro.find.xian"]
                XCTAssertTrue(xian.waitForExistence(timeout: 6))
                xian.tap()
                XCTAssertTrue(canvas.waitForExistence(timeout: 8))
                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "metro-map-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)
            }
        }
    }

    func testPhraseCardsShowFiveScenariosAndBothLanguages() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance, "-UIPreferredContentSizeCategoryName",
                                       "UICTContentSizeCategoryL"]
                app.launch()
                defer { app.terminate() }
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "工具"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                app.buttons["lio.tools.phrase-cards"].tap()
                for category in ["dining", "directions", "taxi", "shopping", "healthcare"] {
                    XCTAssertTrue(app.buttons["lio.phrases.category." + category].exists)
                }
                try app.performAccessibilityAudit(for: .all)
                app.buttons["lio.phrases.category.dining"].tap()
                app.buttons["lio.phrases.card.dining-menu"].tap()
                XCTAssertTrue(app.staticTexts["请问，有英文菜单吗？"].waitForExistence(timeout: 5))
                XCTAssertTrue(app.staticTexts["Is there a menu in English?"].exists)
                XCTAssertTrue(app.buttons["lio.phrases.read.zh-CN"].isHittable)
                XCTAssertTrue(app.buttons["lio.phrases.read.en-US"].isHittable)
                try app.performAccessibilityAudit(for: .all)
                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "phrase-card-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)
                app.buttons["lio.phrases.read.zh-CN"].tap()
                app.buttons["lio.phrases.read.en-US"].tap()
                app.buttons["lio.phrases.done"].tap()
                XCTAssertTrue(app.buttons["lio.phrases.card.dining-menu"].isHittable)
            }
        }
    }

    func testToolsTextReportsOfflineUnavailableOnIOS17() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }
        app.tabBars.buttons["Tools"].tap()
        app.buttons["lio.tools.translation"].tap()
        let editor = app.textViews["lio.translation.input"]
        XCTAssertTrue(editor.waitForExistence(timeout: 6))
        editor.tap()
        editor.typeText("Hello")
        app.buttons["lio.translation.submit"].tap()
        let problem = app.staticTexts["lio.translation.problem"]
        XCTAssertTrue(problem.waitForExistence(timeout: 6))
        XCTAssertTrue(problem.label.contains("iOS 18"))
        XCTAssertFalse(app.staticTexts["lio.translation.result"].exists)
    }

    func testToolsTranslationEntryInBothLanguagesAndAppearances() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-tools-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance]
                app.launch()
                let tools = app.tabBars.buttons[language == "en" ? "Tools" : "工具"]
                XCTAssertTrue(tools.waitForExistence(timeout: 8))
                tools.tap()
                let translation = app.buttons["lio.tools.translation"]
                XCTAssertTrue(translation.waitForExistence(timeout: 6))
                try app.performAccessibilityAudit(for: .all)
                translation.tap()
                XCTAssertTrue(app.buttons["lio.translation.swap"].waitForExistence(timeout: 6))
                XCTAssertTrue(app.textViews["lio.translation.input"].exists)
                try app.performAccessibilityAudit(for: .all)
                let screenshot = XCTAttachment(screenshot: app.screenshot())
                screenshot.name = "translation-\(language)-\(appearance)"
                screenshot.lifetime = .keepAlways
                add(screenshot)
                app.tabBars.buttons[language == "en" ? "Chat" : "聊天"].tap()
                XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 6))
                app.terminate()
            }
        }
    }
}

@MainActor final class LioHomeUITests: XCTestCase {
    func testUnsentOriginalAndDifferentDraftStayVisibleAcrossRelaunchInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-position-persistence-acceptance", "--lio-position-retained-unsent",
                    "-lio.ui.appearance.v1", appearance, "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                    "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
                for _ in 0..<2 {
                    app.launch()
                    let card = app.descendants(matching: .any).matching(identifier: "lio.unsent.message").firstMatch
                    XCTAssertTrue(card.waitForExistence(timeout: 8))
                    XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label == %@ OR value == %@", "Original A", "Original A")).firstMatch.exists)
                    let field = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
                    XCTAssertEqual(field.value as? String, "Different draft B")
                    XCTAssertFalse(app.staticTexts["lio.question"].exists)
                    XCTAssertFalse(app.staticTexts["lio.answer"].exists)
                    XCTAssertFalse(app.staticTexts["lio.opening"].exists)
                    try app.performAccessibilityAudit(for: .all)
                    let shot = XCTAttachment(screenshot: app.screenshot())
                    shot.name = "retained-unsent-\(chinese ? "zh" : "en")-\(appearance)"
                    shot.lifetime = .keepAlways; add(shot)
                    app.terminate()
                }
            }
        }
    }

    func testFailedDraftPersistenceKeepsTextAndOffersARetryControlInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-position-persistence-acceptance", "--lio-position-write-failure",
                "-lio.ui.appearance.v1", "light", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
            app.launch()
            let field = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(field.waitForExistence(timeout: 8))
            field.tap(); field.typeText("x")
            let retained = field.value as? String
            XCTAssertTrue(app.staticTexts["lio.position.notice"].waitForExistence(timeout: 5))
            let retry = app.buttons["lio.position.retry"]
            retry.tap()
            XCTAssertEqual(field.value as? String, retained)
            XCTAssertTrue(app.staticTexts["lio.position.notice"].exists)
            try app.performAccessibilityAudit(for: .all) { issue in
                let detail = XCTAttachment(string: issue.compactDescription + "\n" + (issue.element?.debugDescription ?? "No element") + "\n" + app.debugDescription)
                detail.name = "position-audit"; detail.lifetime = .keepAlways; self.add(detail)
                return false
            }
            app.terminate()
        }
    }

    func testColdRelaunchKeepsTheOriginalChatAndExactDraftInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-position-persistence-acceptance", "-lio.ui.appearance.v1", "light",
                                   "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
            app.launch()
            let answer = app.staticTexts["lio.answer"].firstMatch
            XCTAssertTrue(answer.waitForExistence(timeout: 8))
            let originalAnswer = answer.label
            let field = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            field.tap()
            let old = field.value as? String ?? ""
            if !old.isEmpty && old != (chinese ? "开始聊天" : "Start chatting") {
                field.press(forDuration: 1.2)
                let selectAll = app.descendants(matching: .any).matching(NSPredicate(format: "label IN %@", ["Select All", "全选"])).firstMatch
                XCTAssertTrue(selectAll.waitForExistence(timeout: 3))
                selectAll.tap()
            }
            let value = (chinese ? "未发送草稿 " : "Unsent draft ") + String(Int(ProcessInfo.processInfo.systemUptime * 1000))
            field.typeText(value)
            XCTAssertEqual(field.value as? String, value)
            app.terminate()
            app.launch()
            XCTAssertTrue(answer.waitForExistence(timeout: 8))
            XCTAssertEqual(answer.label, originalAnswer)
            XCTAssertFalse(app.staticTexts["lio.opening"].exists)
            XCTAssertEqual(field.value as? String, value)
            XCTAssertFalse(app.staticTexts["fixture.position.setup-failure"].exists)
            try app.performAccessibilityAudit(for: .all)
            let shot = XCTAttachment(screenshot: app.screenshot()); shot.name = "cold-position-\(chinese ? "zh" : "en")"; shot.lifetime = .keepAlways; add(shot)
            app.terminate()
        }
    }

    func testLocalActivationFailureIsRecoverableWithoutClearingSignInInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-root-activation-failure-acceptance", "-lio.ui.appearance.v1", "light", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
            app.launch()
            let attempts = app.staticTexts["fixture.activation.attempts"]
            XCTAssertTrue(attempts.waitForExistence(timeout: 8))
            let attempted = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == '1'"), object: attempts)
            XCTAssertEqual(XCTWaiter.wait(for: [attempted], timeout: 5), .completed)
            let retry = app.buttons["lio.session.retry"]
            XCTAssertTrue(retry.waitForExistence(timeout: 5))
            XCTAssertTrue(app.staticTexts["lio.session.notice"].label.contains(chinese ? "重新连接" : "Reconnect"))
            XCTAssertFalse(app.progressIndicators.firstMatch.exists)
            XCTAssertFalse(app.staticTexts["fixture.activation.invitation"].exists)
            try app.performAccessibilityAudit(for: .all)
            retry.tap()
            let second = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == '2'"), object: attempts)
            XCTAssertEqual(XCTWaiter.wait(for: [second], timeout: 5), .completed)
            XCTAssertEqual(app.staticTexts["fixture.activation.clears"].label, "0")
            app.terminate()
        }
    }

    func testReadFailurePreservesLoadedConversationInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-read-failure-acceptance", "--lio-read-after-loaded", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
            app.launch()
            let oldAnswer = app.staticTexts["lio.answer"]
            XCTAssertTrue(oldAnswer.waitForExistence(timeout: 8))
            XCTAssertTrue(oldAnswer.label.contains("Your earlier answer is still here."))
            showLioMe(app)
            app.buttons["fixture.read.fail"].tap()
            showLioChat(app)
            XCUIDevice.shared.press(.home)
            app.activate()
            XCTAssertTrue(app.staticTexts["lio.read.failure"].waitForExistence(timeout: 5))
            XCTAssertTrue(oldAnswer.label.contains("Your earlier answer is still here."))
            try app.performAccessibilityAudit(for: .all)
            app.terminate()
        }
    }

    func testReadFailureShowsASpecificNextStepInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            for (flag, english, chineseText) in [("", "offline", "网络"), ("--lio-read-503", "service", "服务"),
                                                ("--lio-read-401", "sign-in", "登录"), ("--lio-read-inactive", "Reconnect", "重新连接")] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-read-failure-acceptance", flag, "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
                app.launch()
                let failure = app.staticTexts["lio.read.failure"]
                XCTAssertTrue(failure.waitForExistence(timeout: 5))
                XCTAssertTrue(failure.label.contains(chinese ? chineseText : english))
                XCTAssertTrue(app.buttons["lio.read.retry"].isEnabled)
                XCTAssertFalse(app.progressIndicators.firstMatch.exists)
                try app.performAccessibilityAudit(for: .all)
                showLioMe(app)
                app.buttons["fixture.read.restore"].tap()
                showLioChat(app)
                XCUIDevice.shared.press(.home)
                app.activate()
                XCTAssertTrue(app.staticTexts["lio.answer"].waitForExistence(timeout: 8))
                XCTAssertFalse(failure.exists)
                app.terminate()
            }
        }
    }

    func testSavedResultWaitsWhileCoveredAndCelebratesOnlyOnce() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-result-visibility-acceptance"]
        app.launch()
        let count = app.staticTexts["fixture.result.count"]
        let card = app.staticTexts["fixture.result.card"]
        let toggle = app.buttons["fixture.result.toggle"]
        XCTAssertTrue(count.waitForExistence(timeout: 8))
        let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == true"), object: card)
        hidden.isInverted = true
        XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 0.4), .completed)
        XCTAssertEqual(count.label, "0")
        toggle.tap()
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        XCTAssertEqual(count.label, "1")
        waitForStreamingControl(toggle); toggle.tap()
        waitForStreamingControl(toggle); toggle.tap()
        XCTAssertEqual(count.label, "1")
        XCTAssertTrue(card.exists)
        try app.performAccessibilityAudit(for: .all)
        app.terminate()
    }

    func testStreamingIncompleteMarkupKeepsTheAdmittedPrefix() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-streaming-acceptance", "--lio-streaming-inline-acceptance",
                                   "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
            app.launch()
            let answer = app.staticTexts["lio.answer"]
            XCTAssertTrue(answer.waitForExistence(timeout: 8))
            let prefix = answer.label
            app.buttons["fixture.streaming.heading"].tap()
            let raw = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS '**'"), object: answer)
            raw.isInverted = true
            XCTAssertEqual(XCTWaiter.wait(for: [raw], timeout: 0.3), .completed)
            XCTAssertEqual(answer.label, prefix)
            app.buttons["fixture.streaming.body"].tap()
            app.buttons["fixture.streaming.finish"].tap()
            let final = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", chinese ? "轻松的安排" : "an easy pace"), object: answer)
            XCTAssertEqual(XCTWaiter.wait(for: [final], timeout: 8), .completed)
            XCTAssertFalse(answer.label.contains("**"))
            XCTAssertFalse(answer.label.contains("["))
            try app.performAccessibilityAudit(for: .all)
            app.terminate()
        }
    }

    func testStreamingMarkdownAndAdmissionInBothLanguages() throws {
        try exerciseStreamingMarkdown(reduceMotion: false)
    }

    func testStreamingMarkdownWithSystemReduceMotion() throws {
        continueAfterFailure = false
        let original = setSimulatorReduceMotion(true)
        defer { _ = setSimulatorReduceMotion(original) }
        try exerciseStreamingMarkdown(reduceMotion: true)
    }

    private func exerciseStreamingMarkdown(reduceMotion: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for chinese in [false, true] {
            for dark in [false, true] {
                app.launchArguments = ["--lio-preview", "--lio-streaming-acceptance",
                                       "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                       "-lio.ui.appearance.v1", dark ? "dark" : "light"]
                if dark { app.launchArguments.append("--lio-streaming-dark-acceptance") }
                app.launch()
                let answer = app.staticTexts["lio.answer"]
                XCTAssertTrue(answer.waitForExistence(timeout: 8))
                XCTAssertEqual(app.staticTexts["fixture.streaming.scheme"].label, dark ? "dark" : "light", app.debugDescription)
                app.buttons["fixture.streaming.heading"].tap()
                let heading = chinese ? "第1天" : "Day 1"
                let partialHeading = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", heading), object: answer)
                partialHeading.isInverted = true
                XCTAssertEqual(XCTWaiter.wait(for: [partialHeading], timeout: 0.3), .completed)
                app.buttons["fixture.streaming.body"].tap()
                let wholeHeading = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", heading), object: answer)
                XCTAssertEqual(XCTWaiter.wait(for: [wholeHeading], timeout: 8), .completed)
                app.buttons["fixture.streaming.finish"].tap()
                let completed = app.staticTexts["fixture.streaming.complete"]
                XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == '1'"), object: completed)], timeout: 8), .completed)
                XCTAssertEqual(app.staticTexts["fixture.streaming.first"].label, "1")
                XCTAssertTrue(answer.label.contains(chinese ? "博物馆" : "Museum"))
                XCTAssertTrue(answer.label.contains(chinese ? "轻松的安排" : "an easy pace"))
                XCTAssertFalse(answer.label.contains("#"))
                XCTAssertFalse(answer.label.contains("**"))
                XCTAssertFalse(answer.label.contains("https://"))
                try app.performAccessibilityAudit(for: .all)
                let image = XCTAttachment(screenshot: app.screenshot())
                image.name = "streaming-\(chinese ? "zh" : "en")-\(dark ? "dark" : "light")-\(reduceMotion ? "reduced" : "normal")"
                image.lifetime = .keepAlways; add(image)
                let final = answer.label
                let show = app.buttons["fixture.streaming.show"]
                waitForStreamingControl(show)
                show.tap()
                XCTAssertFalse(answer.exists)
                XCTAssertEqual(app.staticTexts["fixture.streaming.shown"].label, "0")
                waitForStreamingControl(show)
                show.tap()
                XCTAssertEqual(app.staticTexts["fixture.streaming.shown"].label, "1")
                XCTAssertTrue(answer.waitForExistence(timeout: 2), app.debugDescription)
                XCTAssertEqual(answer.label, final)
                app.buttons["fixture.streaming.unsafe"].tap()
                XCTAssertTrue(app.staticTexts["lio.reply.unavailable"].waitForExistence(timeout: 5))
                XCTAssertFalse(answer.exists)
                app.terminate()
            }
        }
    }

    private func waitForStreamingControl(_ element: XCUIElement) {
        var previous: CGRect?
        let stable = NSPredicate { _, _ in
            guard element.exists, element.isEnabled, element.isHittable else { previous = nil; return false }
            let frame = element.frame
            defer { previous = frame }
            return frame == previous
        }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: stable, object: nil)], timeout: 8), .completed)
    }

    func testWaitingReportsOnlyWhileVisibleAndActive() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-thinking-lifecycle-acceptance"]
        app.launch()
        let appearances = app.staticTexts["fixture.thinking.appearances"]
        let announcements = app.staticTexts["fixture.thinking.announcements"]
        XCTAssertTrue(appearances.waitForExistence(timeout: 12))
        XCTAssertEqual(appearances.label, "0")
        XCTAssertEqual(announcements.label, "0")
        app.buttons["fixture.thinking.change"].tap()
        XCTAssertEqual(announcements.label, "0")
        app.buttons["fixture.thinking.pause"].tap()
        let first = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == '1'"), object: announcements)
        XCTAssertEqual(XCTWaiter.wait(for: [first], timeout: 5), .completed)
        XCTAssertEqual(appearances.label, "1")
        app.buttons["fixture.thinking.pause"].tap()
        app.buttons["fixture.thinking.change"].tap()
        let silent = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label != '1'"), object: announcements)
        silent.isInverted = true
        XCTAssertEqual(XCTWaiter.wait(for: [silent], timeout: 5.2), .completed)
        app.buttons["fixture.thinking.pause"].tap()
        let second = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == '2'"), object: announcements)
        XCTAssertEqual(XCTWaiter.wait(for: [second], timeout: 5), .completed)
        XCTAssertEqual(appearances.label, "1")
        app.buttons["fixture.thinking.show"].tap()
        app.buttons["fixture.thinking.change"].tap()
        XCTAssertEqual(announcements.label, "2")
        XCTAssertEqual(appearances.label, "1")
        app.buttons["fixture.thinking.show"].tap()
        let shown = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == '3'"), object: announcements)
        XCTAssertEqual(XCTWaiter.wait(for: [shown], timeout: 5), .completed)
        XCTAssertEqual(appearances.label, "2")
        app.terminate()
    }

    func testAskAgainRecordsTheNewQuestionTimingInBothLanguages() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-retry-timing-acceptance", "-cj.ui.language.v1", language]
            app.launch()
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(composer.waitForExistence(timeout: 12))
            composer.tap(); composer.typeText("Some travel ideas")
            app.buttons["lio.send"].tap()
            let again = app.buttons["lio.askAgain"]
            XCTAssertTrue(again.waitForExistence(timeout: 8))
            showLioMe(app)
            let count = app.staticTexts["fixture.timing.count"]
            XCTAssertTrue(count.waitForExistence(timeout: 5))
            XCTAssertEqual(count.label, "0")
            showLioChat(app)
            again.tap()
            XCTAssertTrue(app.staticTexts["Here are some travel ideas."].waitForExistence(timeout: 8))
            showLioMe(app)
            XCTAssertTrue(count.waitForExistence(timeout: 5))
            let recorded = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", "1"), object: count)
            XCTAssertEqual(XCTWaiter.wait(for: [recorded], timeout: 8), .completed, count.label)
            showLioChat(app)
            // Same chat-page audit as before #1452; wait for the tab switch to settle before sampling (#1501).
            XCTAssertTrue(app.staticTexts["Here are some travel ideas."].waitForExistence(timeout: 8))
            _ = XCTWaiter.wait(for: [XCTestExpectation(description: "settle after tab switch")], timeout: 1.5)
            try app.performAccessibilityAudit(for: .all)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "retry-timing-" + language
            image.lifetime = .keepAlways
            add(image)
            app.terminate()
        }
    }

    func testThinkingIndicatorStagesAndLineLProgress() {
        exerciseThinkingIndicator(reduceMotion: false)
    }

    func testThinkingIndicatorStillAdvancesWithReduceMotion() {
        continueAfterFailure = false
        let original = setSimulatorReduceMotion(true)
        defer { _ = setSimulatorReduceMotion(original) }
        exerciseThinkingIndicator(reduceMotion: true)
    }

    private func setSimulatorReduceMotion(_ enabled: Bool) -> Bool {
        let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        settings.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        settings.launch()
        let accessibility = settings.cells["Accessibility"]
        for _ in 0..<8 {
            if accessibility.exists && accessibility.isHittable { break }
            settings.swipeUp()
        }
        XCTAssertTrue(accessibility.isHittable, settings.debugDescription)
        accessibility.tap()
        let motion = settings.cells["Motion"]
        XCTAssertTrue(motion.waitForExistence(timeout: 8), settings.debugDescription)
        motion.tap()
        let reduceMotion = settings.switches["Reduce Motion"]
        XCTAssertTrue(reduceMotion.waitForExistence(timeout: 8), settings.debugDescription)
        let original = reduceMotion.value as! String
        XCTAssertTrue(["0", "1"].contains(original))
        if (original == "1") != enabled { reduceMotion.tap() }
        XCTAssertEqual(reduceMotion.value as? String, enabled ? "1" : "0")
        settings.terminate()
        return original == "1"
    }

    private func exerciseThinkingIndicator(reduceMotion: Bool) {
        continueAfterFailure = false
        for language in ["zh-Hans", "en"] {
            let chinese = language == "zh-Hans"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-thinking-acceptance", "-cj.ui.language.v1", language]
            app.launch()
            let indicators = app.staticTexts.matching(identifier: "lio.progress")
            XCTAssertTrue(indicators.firstMatch.waitForExistence(timeout: 12))
            XCTAssertEqual(indicators.count, 5)
            let replying = chinese ? "Lio 正在回复…" : "Lio is replying…"
            for index in 0..<5 { XCTAssertEqual(indicators.element(boundBy: index).label, replying) }
            func value(_ index: Int) -> String { indicators.element(boundBy: index).value as? String ?? "" }
            XCTAssertEqual(value(0), "")
            XCTAssertEqual(value(1), chinese ? "正在整理信息…" : "Pulling the details together…")
            XCTAssertEqual(value(2), chinese ? "这次要多想一会儿…" : "This one is taking a little longer…")
            XCTAssertEqual(value(3), chinese ? "正在比较几家酒店的位置" : "Comparing where the hotels are")
            XCTAssertEqual(value(4), chinese ? "开始安排 3 天行程" : "Starting your 3-day plan")
            let general = NSPredicate(format: "value == %@", chinese ? "正在整理信息…" : "Pulling the details together…")
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: general, object: indicators.element(boundBy: 0))],
                                          timeout: 9), .completed)
            let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            capture.name = "Lio-thinking-" + language + (reduceMotion ? "-reduce-motion" : "")
            capture.lifetime = .keepAlways
            add(capture)
            app.terminate()
        }
    }

    func testEnglish() throws { try exercise("en", question: "How do I take the metro in Shanghai?") }
    func testChinese() throws { try exercise("zh-Hans", question: "在上海怎么坐地铁？") }

    func testInvitationEnglish() throws { try exerciseInvitation("en") }
    func testInvitationChinese() throws { try exerciseInvitation("zh-Hans") }

    func testInterruptionCoversPrivateRootAndPresentedSheet() throws {
        continueAfterFailure = false
        for appearance in ["light", "dark"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-scene-privacy-acceptance", "-lio.ui.appearance.v1", appearance]
            app.launch()
            func verify(_ scope: String, expectedDraft: String) throws {
                let text = app.staticTexts["privacy.\(scope).text"]
                let field = app.textFields["privacy.\(scope).draft"]
                let action = app.buttons["privacy.\(scope).action"]
                XCTAssertTrue(text.waitForExistence(timeout: 10))
                XCTAssertEqual(field.value as? String, expectedDraft)
                let hit = action.frame
                app.buttons["privacy.\(scope).interrupt"].tap()
                XCTAssertFalse(text.exists)
                XCTAssertFalse(field.exists)
                XCTAssertFalse(action.exists)
                XCTAssertFalse(app.navigationBars["Synthetic private \(scope) title"].exists)
                XCTAssertFalse(app.staticTexts["privacy.root.text"].exists)
                XCTAssertFalse(app.textFields["privacy.root.draft"].exists)
                XCTAssertFalse(app.buttons["privacy.root.action"].exists)
                app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: hit.midX, dy: hit.midY)).tap()
                try app.performAccessibilityAudit(for: .all)
                let image = XCTAttachment(screenshot: app.screenshot())
                image.name = "scene-private-\(scope)-\(appearance)"
                image.lifetime = .keepAlways
                add(image)
                app.buttons["lio.privacy.test.resume"].tap()
                XCTAssertTrue(text.waitForExistence(timeout: 8))
                XCTAssertEqual(app.staticTexts["privacy.\(scope).actions"].label, "0")
                XCTAssertEqual(field.value as? String, expectedDraft)
            }
            try verify("root", expectedDraft: "Synthetic root draft")
            app.buttons["privacy.open-sheet"].tap()
            try verify("sheet", expectedDraft: "Synthetic sheet draft")
            app.buttons["privacy.close-sheet"].tap()
            XCTAssertTrue(app.staticTexts["privacy.root.text"].waitForExistence(timeout: 8))
            app.terminate()
        }
    }

    func testSessionRecoveryKeepsExplicitActionsInBothLanguagesAndAppearances() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let chinese = language == "zh-Hans"
                app.launchArguments = ["--lio-preview", "--lio-session-recovery-acceptance",
                                       "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance]
                app.launch()
                let recovery = app.descendants(matching: .any).matching(identifier: "lio.session.recovery").firstMatch
                XCTAssertTrue(recovery.waitForExistence(timeout: 12))
                XCTAssertTrue(app.staticTexts[chinese ? "正在恢复对话…" : "Restoring your chat…"].exists)
                XCTAssertFalse(app.buttons["lio.session.retry"].exists)
                XCTAssertFalse(app.secureTextFields["demo.invite.code"].exists)
                XCTAssertFalse(app.textViews["lio.question"].exists)
                XCTAssertFalse(app.staticTexts["lio.answer"].exists)
                try app.performAccessibilityAudit(for: .all)
                let loading = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                loading.name = "Lio-session-loading-" + language + "-" + appearance
                loading.lifetime = .keepAlways
                add(loading)

                app.buttons["synthetic.recovery.offline"].tap()
                let retry = app.buttons["lio.session.retry"]
                XCTAssertTrue(retry.waitForExistence(timeout: 5))
                XCTAssertEqual(retry.label, chinese ? "重试" : "Try again")
                XCTAssertEqual(app.staticTexts["lio.session.notice"].label,
                               chinese ? "暂时连接不上，登录信息仍已保留。"
                                   : "Couldn’t connect. Your sign-in is still saved.")
                try app.performAccessibilityAudit(for: .all)
                let offline = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                offline.name = "Lio-session-offline-" + language + "-" + appearance
                offline.lifetime = .keepAlways
                add(offline)
                retry.tap()
                XCTAssertEqual(app.staticTexts["synthetic.recovery.retry-count"].label, "1")
                XCTAssertFalse(retry.exists)
                let signout = app.buttons["lio.session.signout"]
                XCTAssertEqual(signout.label, chinese ? "退出登录" : "Sign out")
                signout.tap()
                XCTAssertTrue(app.staticTexts["synthetic.recovery.signedout"].waitForExistence(timeout: 5))
                app.terminate()
            }
        }
    }

    func testAppearanceBelowLanguagePersistsInBothLanguages() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            let dark = chinese ? "深色" : "Dark"
            let light = chinese ? "浅色" : "Light"
            let system = chinese ? "跟随系统" : "System"
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
            app.launch()
            // #1452: language and appearance moved from the chat menu to the Me tab.
            let me = app.tabBars.buttons[chinese ? "我的" : "Me"]
            XCTAssertTrue(me.waitForExistence(timeout: 12))
            me.tap()
            let appearance = app.buttons["lio.appearance"]
            let languagePicker = app.buttons["lio.language"]
            XCTAssertTrue(appearance.waitForExistence(timeout: 8))
            XCTAssertGreaterThan(appearance.frame.minY, languagePicker.frame.minY)
            appearance.tap()
            app.buttons[dark].tap()
            XCTAssertTrue(appearance.label.contains(dark), appearance.debugDescription)
            let darkCapture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            darkCapture.name = "Lio-dark-" + language
            darkCapture.lifetime = .keepAlways
            add(darkCapture)

            app.terminate()
            app.launch()
            XCTAssertTrue(me.waitForExistence(timeout: 12))
            me.tap()
            XCTAssertTrue(appearance.waitForExistence(timeout: 8))
            XCTAssertTrue(appearance.label.contains(dark), appearance.debugDescription)
            let menuCapture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            menuCapture.name = "Lio-appearance-menu-" + language
            menuCapture.lifetime = .keepAlways
            add(menuCapture)
            appearance.tap()
            app.buttons[light].tap()
            XCTAssertTrue(appearance.label.contains(light), appearance.debugDescription)
            let lightCapture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            lightCapture.name = "Lio-light-" + language
            lightCapture.lifetime = .keepAlways
            add(lightCapture)
            XCTAssertTrue(appearance.waitForExistence(timeout: 5))
            appearance.tap()
            if !app.buttons[system].waitForExistence(timeout: 3) { appearance.tap() }
            XCTAssertTrue(app.buttons[system].waitForExistence(timeout: 5))
            app.buttons[system].tap()
            XCTAssertTrue(appearance.label.contains(system), appearance.debugDescription)
            app.terminate()
        }
    }

    func testOpeningGreetingReturnsAfterBackgroundWithoutResettingTheChat() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
            app.launch()
            let greeting = app.staticTexts["lio.opening"]
            XCTAssertTrue(greeting.waitForExistence(timeout: 12))
            enterSampleQuestion(in: app, index: 0)
            app.buttons["lio.send"].tap()
            let question = app.textViews["lio.question"], answer = app.staticTexts["lio.answer"]
            XCTAssertTrue(answer.waitForExistence(timeout: 8))
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            composer.tap(); composer.typeText("Unsent follow-up")
            let sendReady = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: app.buttons["lio.send"])
            XCTAssertEqual(XCTWaiter.wait(for: [sendReady], timeout: 8), .completed)
            let sentText = question.value as? String, replyText = answer.label
            XCTAssertNotNil(sentText)
            XCUIDevice.shared.press(.home)
            XCTAssertTrue(app.wait(for: .runningBackground, timeout: 5) || app.state == .runningBackgroundSuspended)
            app.activate()
            XCTAssertTrue(question.waitForExistence(timeout: 8))
            XCTAssertEqual(composer.value as? String, "Unsent follow-up")
            app.scrollViews.firstMatch.swipeDown()
            app.scrollViews.firstMatch.swipeDown()
            XCTAssertTrue(greeting.exists)
            XCTAssertEqual(question.value as? String, sentText)
            XCTAssertEqual(answer.label, replyText)
            XCTAssertLessThan(greeting.frame.minY, question.frame.minY)
            XCTAssertEqual(app.staticTexts.matching(identifier: "lio.opening").count, 1)
            XCTAssertEqual(app.textViews.matching(identifier: "lio.question").count, 1)
            app.terminate()
        }
    }

    func testNewChatAndHistoryKeepMessagesAndDraftsSeparate() {
        exerciseChatHistory("en")
    }

    func testChineseNewChatKeepsHistoryAndDraftsSeparate() {
        exerciseChatHistory("zh-Hans")
    }

    func testRecreatedClientReturnsToEnglishConversationAndDraft() throws { try exerciseRecreatedChat("en") }
    func testRecreatedClientReturnsToChineseConversationAndDraft() throws { try exerciseRecreatedChat("zh-Hans") }

    func testSavedChatRestoresWhileAnUnrelatedFirstSendNeedsRecovery() throws {
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                try exerciseRecreatedChat(language, appearance: appearance, unrelatedRecovery: true)
            }
        }
    }

    private func exerciseRecreatedChat(_ language: String, appearance: String = "light", unrelatedRecovery: Bool = false) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "--lio-chat-recovery-acceptance", "-cj.ui.language.v1", language]
        app.launchArguments += ["--lio-chat-before-stage-acceptance", "-lio.ui.appearance.v1", appearance]
        if unrelatedRecovery { app.launchArguments += ["--lio-chat-unrelated-recovery-acceptance"] }
        app.launch()
        defer { app.terminate() }
        let menu = app.buttons["lio.menu"]
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(composer.waitForExistence(timeout: 12))
        XCTAssertEqual(composer.value as? String, language == "en" ? "A question before staging" : "还没发出的合成问题")
        XCTAssertTrue(app.buttons["lio.send"].isEnabled)
        menu.tap()
        XCTAssertTrue(app.buttons["lio.chat.new"].waitForExistence(timeout: 8))
        app.terminate()
        app.launchArguments.removeAll { $0 == "--lio-chat-before-stage-acceptance" }
        app.launch()
        XCTAssertTrue(menu.waitForExistence(timeout: 12))
        menu.tap(); app.buttons["lio.chat.new"].tap()
        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        enterSampleQuestion(in: app, index: 0); app.buttons["lio.send"].tap()
        XCTAssertTrue(app.staticTexts["A separate reply."].waitForExistence(timeout: 12))
        composer.tap(); composer.typeText("My unsent follow-up")
        showLioMe(app); app.buttons["synthetic.chat.recreate"].tap(); showLioChat(app)
        XCTAssertTrue(app.staticTexts["A separate reply."].waitForExistence(timeout: 12), app.debugDescription)
        XCTAssertFalse(app.staticTexts["An earlier reply."].exists)
        XCTAssertEqual(composer.value as? String, "My unsent follow-up")
        XCTAssertFalse(app.otherElements["lio.chat.recovery"].exists)
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        if unrelatedRecovery {
            try app.performAccessibilityAudit(for: .all)
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "restored-chat-\(language)-\(appearance)"
            shot.lifetime = .keepAlways; add(shot)
        }
    }

    func testFailedRestoreNamesTheServiceProblemAndShowsOnDeviceNotes() throws {
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                try exerciseFailedRestore(language, appearance: appearance)
            }
        }
    }

    private func exerciseFailedRestore(_ language: String, appearance: String) throws {
        continueAfterFailure = false
        let english = language == "en"
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "--lio-chat-recovery-acceptance",
                               "--lio-chat-selected-lookup-failure-acceptance", "-cj.ui.language.v1", language,
                               "-lio.ui.appearance.v1", appearance]
        app.launch()
        defer { app.terminate() }
        let menu = app.buttons["lio.menu"]
        XCTAssertTrue(menu.waitForExistence(timeout: 12))
        menu.tap(); app.buttons["lio.chat.new"].tap()
        XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 8))
        enterSampleQuestion(in: app, index: 0); app.buttons["lio.send"].tap()
        showLioMe(app); app.buttons["synthetic.chat.recreate"].tap(); showLioChat(app)
        let service = english ? "Our service is having a problem or is under maintenance. This isn’t your connection."
                              : "服务暂时出错或正在维护，不是你的网络问题。"
        XCTAssertTrue(app.staticTexts[service].waitForExistence(timeout: 12), app.debugDescription)
        XCTAssertFalse(app.staticTexts[english ? "Couldn’t open your conversation. Try again when you’re connected."
                                               : "暂时无法打开对话，请联网后重试。"].exists)
        XCTAssertTrue(app.staticTexts[english ? "Please try again later. Your messages and draft stay on this device."
                                              : "请稍后再试。你的消息和草稿仍保留在本机。"].exists)
        try app.performAccessibilityAudit(for: .all)
        attach(app, "restore-service-\(language)-\(appearance)")
        app.buttons[english ? "View problem notes" : "查看问题记录"].tap()
        let list = app.descendants(matching: .any).matching(identifier: "lio.problems.list").firstMatch
        XCTAssertTrue(list.waitForExistence(timeout: 8), app.debugDescription)
        let notes = (list.value as? String) ?? list.label
        XCTAssertTrue(notes.contains("service · firstSendLookup · first-send-lookup · HTTP 503"), notes)
        XCTAssertFalse(notes.contains("SYNTHETIC"))
        try app.performAccessibilityAudit(for: .all)
        attach(app, "restore-notes-\(language)-\(appearance)")
        app.buttons["lio.problems.done"].tap()
        // Retrying shows the same cause again; the uncertain first send is never posted twice.
        app.buttons[english ? "Try again" : "重试"].tap()
        XCTAssertTrue(app.staticTexts[service].waitForExistence(timeout: 12), app.debugDescription)
    }

    private func attach(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testNewChatCanAcceptAnotherMessageAfterAnInputRefusal() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "--lio-chat-first-refusal-acceptance",
                               "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let menu = app.buttons["lio.menu"]
        XCTAssertTrue(menu.waitForExistence(timeout: 12))
        menu.tap()
        app.buttons["lio.chat.new"].tap()
        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        enterSampleQuestion(in: app, index: 0)
        let send = app.buttons["lio.send"]
        send.tap()
        let failure = app.staticTexts["lio.failure"]
        XCTAssertTrue(failure.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertEqual(failure.label, "这条消息没发出去，请换个说法再试。")
        XCTAssertFalse(app.buttons["lio.resend"].exists)
        XCTAssertFalse(app.staticTexts["A separate reply."].exists)

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap()
        composer.typeText("A fresh question")
        send.tap()
        XCTAssertTrue(app.staticTexts["A separate reply."].waitForExistence(timeout: 12), app.debugDescription)
    }

    private func exerciseChatHistory(_ language: String) {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        let chinese = language == "zh-Hans"
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let menu = app.buttons["lio.menu"]
        let oldReply = app.staticTexts["An earlier reply."]
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        menu.tap()
        let newChat = app.buttons["lio.chat.new"]
        XCTAssertEqual(newChat.label, chinese ? "新对话" : "New chat")
        newChat.tap()
        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["lio.opening"].exists)
        XCTAssertFalse(oldReply.exists)
        XCTAssertFalse(app.textViews["lio.question"].exists)
        enterSampleQuestion(in: app, index: 0)
        let firstQuestion = chinese ? "在上海怎么坐地铁？" : "How do I take the metro in Shanghai?"
        XCTAssertEqual(composer.value as? String, firstQuestion)
        app.buttons["lio.send"].tap()
        let newReply = app.staticTexts["A separate reply."]
        XCTAssertTrue(newReply.waitForExistence(timeout: 12), app.debugDescription)
        XCTAssertFalse(oldReply.exists)
        composer.tap()
        let draft = "A follow up draft"
        composer.typeText(draft)

        func openHistory(_ title: String) {
            menu.tap()
            let history = app.buttons["lio.chat.history"]
            XCTAssertEqual(history.label, chinese ? "历史对话" : "Chat history")
            history.tap()
            let row = app.buttons.matching(identifier: "lio.chat.history.row")
                .matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 8))
            row.tap()
        }
        openHistory(chinese ? "最早的对话" : "First conversation")
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["lio.opening"].exists)
        XCTAssertFalse(newReply.exists)
        XCTAssertNotEqual(composer.value as? String, draft)
        openHistory(firstQuestion)
        XCTAssertTrue(newReply.waitForExistence(timeout: 8))
        XCTAssertFalse(oldReply.exists)
        XCTAssertEqual(composer.value as? String, draft)
    }

    private func exerciseInvitation(_ language: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-onboarding-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        let field = app.secureTextFields["demo.invite.code"]
        let proceed = app.buttons["demo.invite.continue"]
        let consent = app.descendants(matching: .any).matching(identifier: "demo.invite.consent").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 12))
        XCTAssertFalse(proceed.isEnabled)
        app.buttons["demo.invite.restore"].tap()
        XCTAssertTrue(consent.waitForExistence(timeout: 8))
        app.buttons["lio.invite.back"].tap()
        XCTAssertTrue(field.waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["lio.menu"].exists)

        field.tap()
        field.typeText("D1-aaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbb")
        proceed.tap()
        XCTAssertTrue(consent.waitForExistence(timeout: 8))
        try app.performAccessibilityAudit(for: .all)
        app.buttons["lio.invite.back"].tap()
        XCTAssertTrue(proceed.waitForExistence(timeout: 8))
        XCTAssertTrue(proceed.isEnabled)
        XCTAssertFalse(app.buttons["lio.menu"].exists)
        proceed.tap()
        app.buttons["demo.invite.signin"].tap()
        XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.buttons["lio.example.0"].exists)
    }

    func testJourneyEnglish() throws { try exerciseJourney("en") }
    func testJourneyChinese() throws { try exerciseJourney("zh-Hans") }

    func testTitledMemoryJourneyEnglish() throws { try exerciseJourney("en", titledReads: true) }
    func testTitledMemoryJourneyChinese() throws { try exerciseJourney("zh-Hans", titledReads: true) }

    private func exerciseJourney(_ language: String, titledReads: Bool = false) throws {
        continueAfterFailure = false
        let chinese = language == "zh-Hans"
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "-cj.ui.language.v1", language]
        if titledReads { app.launchArguments.append("--lio-memory-titled-acceptance") }
        app.launch()
        defer { app.terminate() }

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        let send = app.buttons["lio.send"]
        let chat = app.tabBars.buttons[chinese ? "聊天" : "Chat"]
        let trips = app.tabBars.buttons[chinese ? "行程" : "Trips"]
        func reply(_ text: String) {
            XCTAssertTrue(app.staticTexts[text].waitForExistence(timeout: 10), app.debugDescription)
        }
        func ask(_ text: String) {
            composer.tap()
            composer.typeText(text)
            XCTAssertTrue(send.isEnabled)
            send.tap()
        }
        func reveal(_ control: XCUIElement) {
            for _ in 0..<4 {
                if control.isHittable { return }
                app.swipeUp()
            }
            XCTAssertTrue(control.isHittable, app.debugDescription)
        }

        let metro = app.buttons["lio.example.0"]
        XCTAssertTrue(metro.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        XCTAssertFalse(app.textViews["lio.question"].exists)
        send.tap()
        XCTAssertTrue(app.staticTexts[chinese ? "Lio 正在回复…" : "Lio is replying…"]
            .waitForExistence(timeout: 3))
        reply(chinese ? "跟着地铁线路指示牌走。" : "Follow the signs for your metro line.")
        XCTAssertFalse(app.buttons["lio.source"].exists)
        XCTAssertFalse(app.staticTexts[chinese ? "正在查旅行信息…" : "Checking travel information…"].exists)

        ask(chinese ? "帮我规划北京两天" : "Plan two days in Beijing")
        reply(chinese ? "你想慢慢逛吗？" : "Would you like a slower pace?")
        XCTAssertFalse(app.buttons["lio.trip.show"].exists)
        ask(chinese ? "慢一点" : "Take it slow")
        reply(chinese ? "北京行程已保存。" : "I saved your Beijing trip.")
        let show = app.buttons["lio.trip.show"]
        reveal(show)
        show.tap()
        let hotel = chinese ? "酒店入住" : "Hotel check-in"
        let park = chinese ? "公园散步" : "Park walk"
        let museum = chinese ? "美术馆" : "Art museum"
        let card = app.buttons.containing(.staticText, identifier: chinese ? "北京行程" : "Beijing trip").firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 8))
        card.tap()
        func selectDay(_ number: Int) {
            let button = app.buttons["lio.trip.select-day.\(number)"]
            if !button.isHittable { app.swipeDown() }
            XCTAssertTrue(button.isHittable)
            button.tap()
        }
        selectDay(1)
        reply(hotel)
        selectDay(2)
        reply(park)
        chat.tap()

        ask(chinese ? "把第二天下午换成美术馆" : "Change the second day to the art museum")
        reply(chinese ? "第二天下午已经改好了。" : "I changed the second afternoon.")
        let undo = app.buttons["lio.chat.trip.undo"]
        XCTAssertTrue(undo.waitForExistence(timeout: 10), app.debugDescription)
        trips.tap()
        selectDay(1)
        reply(hotel)
        selectDay(2)
        reply(museum)
        XCTAssertFalse(app.staticTexts[park].exists)
        chat.tap()
        reveal(undo)
        undo.tap()
        trips.tap()
        selectDay(2)
        reply(park)
        XCTAssertFalse(app.staticTexts[museum].exists)
        selectDay(1)
        reply(hotel)
        XCTAssertFalse(app.staticTexts[museum].exists)
        let backToTrips = app.navigationBars.buttons[chinese ? "行程" : "Trips"].firstMatch
        XCTAssertTrue(backToTrips.isHittable)
        backToTrips.tap()
        let previous = app.buttons["lio.trip.history"]
        XCTAssertTrue(previous.waitForExistence(timeout: 6))
        previous.tap()
        XCTAssertTrue(app.buttons["lio.trip.undo"].waitForExistence(timeout: 6))
        chat.tap()

        ask(chinese ? "我喜欢安静的酒店" : "I prefer quiet hotels")
        let remember = app.buttons["lio.memory.remember"]
        XCTAssertTrue(remember.waitForExistence(timeout: 10))
        XCTAssertEqual(app.buttons.matching(identifier: "lio.memory.remember").count, 1)
        let remembered = app.staticTexts[chinese ? "已记住" : "Remembered"]
        XCTAssertFalse(remembered.exists)
        reveal(remember)
        reply(chinese ? "记住：你喜欢安静的酒店？" : "Remember: You like quiet hotels?")
        remember.tap()
        XCTAssertTrue(remembered.waitForExistence(timeout: 10))
        XCTAssertFalse(remember.exists)
        ask(chinese ? "我适合住哪种酒店" : "What kind of hotel suits me?")
        reply(chinese ? "你喜欢安静的酒店。" : "You like quiet hotels.")

        openLioMemory(app, chinese: chinese)
        let preference = chinese ? "你喜欢安静的酒店" : "You like quiet hotels"
        let editedPreference = chinese ? "你喜欢安静且靠近地铁的酒店" : "You like quiet hotels near the metro"
        let otherPreference = chinese ? "你偏好靠过道的座位" : "You prefer an aisle seat"
        let otherMemory = app.buttons["lio.memory.card.aisle-seat"]
        XCTAssertTrue(otherMemory.waitForExistence(timeout: 8))
        XCTAssertEqual(otherMemory.value as? String, otherPreference)
        let saved = app.buttons["lio.memory.card.quiet-hotel"]
        XCTAssertTrue(saved.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertEqual(saved.value as? String, preference)
        if titledReads {
            XCTAssertTrue(saved.label.contains(chinese ? "安静酒店" : "Quiet hotels"))
            XCTAssertFalse(saved.label.contains(preference))
        }
        saved.tap()
        let edit = app.buttons["lio.memory.edit"]
        XCTAssertTrue(edit.waitForExistence(timeout: 8), app.debugDescription)
        edit.tap()
        let editor = app.descendants(matching: .any).matching(identifier: "lio.memory.editor").firstMatch
        XCTAssertTrue(editor.waitForExistence(timeout: 8))
        editor.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.2)).tap()
        editor.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: preference.count) + editedPreference)
        XCTAssertEqual(editor.value as? String, editedPreference)
        let save = app.buttons["lio.memory.save"]
        reveal(save)
        save.tap()
        reply(editedPreference)
        reply(chinese ? "已保存。" : "Saved.")

        let delete = app.buttons["lio.memory.delete"]
        let confirm = app.buttons["lio.memory.delete.confirm"]
        let deletionTitle = chinese ? "删除记忆" : "Delete memory"
        let done = app.navigationBars[deletionTitle].buttons[chinese ? "完成" : "Done"]
        reveal(delete)
        delete.tap()
        XCTAssertTrue(confirm.waitForExistence(timeout: 8), app.debugDescription)
        let range = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@",
            chinese ? "聊天和已保存行程会保留" : "Your chats and saved trips stay")).firstMatch
        XCTAssertTrue(range.exists)
        done.tap()
        reply(editedPreference)
        reveal(delete)
        delete.tap()
        XCTAssertTrue(confirm.waitForExistence(timeout: 8))
        reveal(confirm)
        confirm.tap()
        XCTAssertTrue(app.staticTexts[chinese ? "Lio 已停止使用这条记忆。" : "Lio has stopped using this memory."]
            .waitForExistence(timeout: 25), app.debugDescription)
        reply(chinese ? "线上清理已完成。" : "Online cleanup is complete.")
        reply(chinese ? "本机已清理这条记忆的保存和编辑记录。"
                      : "This device’s records of saving and editing this memory were cleared.")
        done.tap()
        XCTAssertTrue(otherMemory.waitForExistence(timeout: 8))
        XCTAssertEqual(otherMemory.value as? String, otherPreference)
        XCTAssertFalse(app.buttons["lio.memory.card.quiet-hotel"].exists)
        closeLioMemory(app)
        chat.tap()
        ask(chinese ? "再说说我适合住哪种酒店" : "Remind me what kind of hotel suits me")
        reply(chinese ? "你喜欢什么样的酒店？" : "Tell me what kind of hotel you like.")
    }

    func testTripEmptyStateInvitesConversationInBothLanguages() throws {
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
            app.launch()
            XCTAssertTrue(app.tabBars.buttons[chinese ? "行程" : "Trips"].waitForExistence(timeout: 12))
            app.tabBars.buttons[chinese ? "行程" : "Trips"].tap()
            XCTAssertTrue(app.staticTexts[chinese ? "还没有行程" : "No trips yet"].waitForExistence(timeout: 8))
            let chat = app.buttons[chinese ? "和 Lio 聊聊" : "Chat with Lio"]
            XCTAssertTrue(chat.isHittable)
            try app.performAccessibilityAudit(for: .all)
            let attachment = XCTAttachment(screenshot: app.screenshot())
            attachment.name = "trip-empty-\(language)"
            attachment.lifetime = .keepAlways
            add(attachment)
            chat.tap()
            XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 8))
            app.terminate()
        }
    }

    func testTripTimelineDarkAndLargestTypeInBothLanguages() throws {
        for language in ["en", "zh-Hans"] {
            for largest in [false, true] {
                try exerciseTrip(language,
                    clarification: language == "en" ? "For three days in Beijing" : "北京三天",
                    trips: language == "en" ? "Trips" : "行程", day: language == "en" ? "Day 1" : "第 1 天",
                    fixed: language == "en" ? "Hotel check-in" : "酒店入住", largest: largest,
                    appearance: largest ? "light" : "dark")
            }
        }
    }

    func testTripListOnlyShowsTheSavedSummaryFields() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", appearance]
                app.launchEnvironment = ["G2C_LIO_PREVIEW_TRIP": "__LIO_RECORDED_TRIP_FIXTURE__"]
                app.launch()
                let tab = app.tabBars.buttons[language == "en" ? "Trips" : "行程"]
                XCTAssertTrue(tab.waitForExistence(timeout: 12))
                tab.tap()
                let card = app.buttons["Draft"]
                XCTAssertTrue(card.waitForExistence(timeout: 8))
                XCTAssertEqual(card.label, "Draft")
                XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "lio.trip.route-map").firstMatch.exists)
                try app.performAccessibilityAudit(for: .all)
                let attachment = XCTAttachment(screenshot: app.screenshot())
                attachment.name = "trip-list-\(language)-\(appearance)"
                attachment.lifetime = .keepAlways
                add(attachment)
                app.terminate()
            }
        }
    }

    func testMemoryTitlesShowServiceTextAndKeepCompleteOriginals() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for style in ["light", "dark", "largest"] {
                let chinese = language == "zh-Hans"
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "--lio-memory-grid-acceptance",
                                       "--lio-memory-titled-acceptance", "-cj.ui.language.v1", language,
                                       "-lio.ui.appearance.v1", style == "dark" ? "dark" : "light"]
                if style == "largest" {
                    app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
                }
                app.launch()
                openLioMemory(app, chinese: chinese)
                let card = app.buttons["lio.memory.card.aisle-seat"]
                XCTAssertTrue(card.waitForExistence(timeout: 8))
                let original = chinese ? "你偏好靠过道的座位" : "You prefer an aisle seat"
                XCTAssertTrue(card.label.contains(chinese ? "过道座位" : "Aisle seat"))
                XCTAssertEqual(card.value as? String, original)
                XCTAssertFalse(card.label.contains(original))
                if style != "largest" {
                    let food = app.buttons["lio.memory.card.food-interest"]
                    let museum = app.buttons["lio.memory.card.museum-stops"]
                    XCTAssertEqual(food.label, chinese ? "偏好" : "Preference")
                    XCTAssertEqual(food.value as? String, chinese ? "你喜欢尝试当地美食" : "You enjoy local food")
                    XCTAssertEqual(museum.label, chinese ? "偏好" : "Preference")
                    XCTAssertEqual(museum.value as? String, chinese ? "你喜欢参观美术馆" : "You enjoy art museums")
                    XCTAssertTrue(app.buttons["lio.memory.card.city-walks"].label.contains(chinese ? "已停用" : "Deactivated"))
                }
                try app.performAccessibilityAudit(for: .all)
                let capture = XCTAttachment(screenshot: app.screenshot())
                capture.name = "memory-titles-\(language)-\(style)"
                capture.lifetime = .keepAlways
                add(capture)
                card.tap()
                XCTAssertTrue(app.staticTexts[original].waitForExistence(timeout: 8))
                let edit = app.buttons["lio.memory.edit"]
                for _ in 0..<3 where !edit.isHittable { app.swipeUp() }
                XCTAssertTrue(edit.isHittable)
                edit.tap()
                let editor = app.descendants(matching: .any).matching(identifier: "lio.memory.editor").firstMatch
                XCTAssertEqual(editor.value as? String, original)
                app.terminate()
            }
        }
    }

    func testMemoryDeactivationRecoversTheOriginalActionAndKeepsTheBody() throws {
        continueAfterFailure = false
        for (language, appearance) in [("en", "light"), ("en", "dark"), ("zh-Hans", "light"), ("zh-Hans", "dark")] {
            let chinese = language == "zh-Hans"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "--lio-memory-grid-acceptance",
                                   "--lio-memory-titled-acceptance", "-cj.ui.language.v1", language,
                                   "-lio.ui.appearance.v1", appearance]
            app.launch()
            openLioMemory(app, chinese: chinese)
            let card = app.buttons["lio.memory.card.quiet-hotel"]
            XCTAssertTrue(card.waitForExistence(timeout: 8))
            let original = try XCTUnwrap(card.value as? String)
            for deactivated in [true, false] {
                for _ in 0..<3 where !card.isHittable { app.swipeUp() }
                card.tap()
                XCTAssertTrue(app.staticTexts[original].waitForExistence(timeout: 8))
                let action = app.buttons[deactivated ? "lio.memory.pause" : "lio.memory.resume"]
                for _ in 0..<3 where !action.isHittable { app.swipeUp() }
                XCTAssertTrue(action.isHittable)
                action.tap()
                let next = app.buttons[deactivated ? "lio.memory.resume" : "lio.memory.pause"]
                XCTAssertTrue(next.waitForExistence(timeout: 12), app.debugDescription)
                XCTAssertTrue(app.staticTexts[original].exists)
                XCTAssertEqual(app.staticTexts[chinese ? "Lio 暂时不用这条记忆。"
                    : "Lio isn’t using this memory."].exists, deactivated)
                try app.performAccessibilityAudit(for: .all)
                if deactivated {
                    let image = XCTAttachment(screenshot: app.screenshot())
                    image.name = "memory-control-\(language)-\(appearance)"
                    image.lifetime = .keepAlways
                    add(image)
                }
                app.navigationBars.buttons.element(boundBy: 0).tap()
                XCTAssertTrue(card.waitForExistence(timeout: 8))
                XCTAssertEqual(card.value as? String, original)
                XCTAssertEqual(card.label.contains(chinese ? "已停用" : "Deactivated"), deactivated)
                try app.performAccessibilityAudit(for: .all)
            }
            app.terminate()
        }
    }

    func testInvalidMemoryTitleDoesNotBecomeASuccessfulBodyFallback() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "--lio-memory-grid-acceptance",
                                   "--lio-memory-titled-acceptance", "--lio-memory-titled-invalid-acceptance",
                                   "-cj.ui.language.v1", language]
            app.launch()
            openLioMemory(app, chinese: chinese)
            XCTAssertTrue(app.staticTexts[chinese ? "暂时看不到你的记忆，下拉再试一次。"
                : "Couldn’t show your memories. Pull down to try again."].waitForExistence(timeout: 8))
            XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "lio.memory.card.")).count, 0)
            try app.performAccessibilityAudit(for: .all)
            app.terminate()
        }
    }

    func testMemoryGridLayoutsKeepTheFullBodyAndDisabledState() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for style in ["light", "dark", "largest"] {
                let chinese = language == "zh-Hans"
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "--lio-memory-grid-acceptance",
                                       "-cj.ui.language.v1", language, "-lio.ui.appearance.v1", style == "dark" ? "dark" : "light"]
                if style == "largest" {
                    app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
                }
                app.launch()
                openLioMemory(app, chinese: chinese)
                let first = app.buttons["lio.memory.card.aisle-seat"]
                let second = app.buttons["lio.memory.card.city-walks"]
                XCTAssertTrue(first.waitForExistence(timeout: 8), app.debugDescription)
                XCTAssertTrue(second.exists)
                XCTAssertEqual(first.frame.width, second.frame.width, accuracy: 1)
                XCTAssertEqual(first.frame.height, second.frame.height, accuracy: 1)
                XCTAssertEqual(first.frame.height, first.frame.width, accuracy: 1)
                for card in app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "lio.memory.card.")).allElementsBoundByIndex {
                    XCTAssertEqual(card.frame.height, first.frame.height, accuracy: 1)
                    XCTAssertEqual(card.frame.width, first.frame.width, accuracy: 1)
                }
                if style == "largest" {
                    XCTAssertGreaterThan(second.frame.minY, first.frame.maxY)
                } else {
                    XCTAssertEqual(first.frame.minY, second.frame.minY, accuracy: 2)
                    XCTAssertGreaterThan(second.frame.minX, first.frame.maxX)
                }
                try app.performAccessibilityAudit(for: .all) { issue in
                    let detail = XCTAttachment(string: String(describing: issue.auditType) + "\n" +
                                               (issue.element?.debugDescription ?? "No element supplied by audit") + "\n" + app.debugDescription)
                    detail.name = "Memory grid AX diagnostic"
                    detail.lifetime = .keepAlways
                    self.add(detail)
                    return false
                }
                let attachment = XCTAttachment(screenshot: app.screenshot())
                attachment.name = "memory-grid-\(language)-\(style)"
                attachment.lifetime = .keepAlways
                add(attachment)
                let disabled = app.buttons["lio.memory.card.city-walks"]
                if !disabled.isHittable { app.swipeUp() }
                XCTAssertTrue(disabled.isHittable)
                let body = try XCTUnwrap(disabled.value as? String)
                XCTAssertTrue(body.contains(chinese ? "当地小店" : "local shops"))
                XCTAssertTrue(disabled.label.contains(chinese ? "已停用" : "Deactivated"))
                disabled.tap()
                XCTAssertTrue(app.staticTexts[body].waitForExistence(timeout: 8))
                XCTAssertTrue(app.staticTexts[chinese ? "Lio 暂时不用这条记忆。" : "Lio isn’t using this memory."].exists)
                let edit = app.buttons["lio.memory.edit"]
                for _ in 0..<3 where !edit.isHittable { app.swipeUp() }
                XCTAssertTrue(edit.isHittable)
                edit.tap()
                let editors = app.descendants(matching: .any).matching(identifier: "lio.memory.editor")
                let editor = editors.firstMatch
                XCTAssertTrue(editor.waitForExistence(timeout: 8), app.debugDescription)
                XCTAssertEqual(editors.count, 1)
                XCTAssertTrue(editor.isEnabled)
                XCTAssertEqual(editor.value as? String, body)

                app.terminate()
            }
        }
    }

    func testTripEnglish() throws {
        try exerciseTrip("en", clarification: "For three days in Beijing", trips: "Trips", day: "Day 1", fixed: "Hotel check-in")
    }

    func testTripChinese() throws {
        try exerciseTrip("zh-Hans", clarification: "北京三天", trips: "行程", day: "第 1 天", fixed: "酒店入住")
    }

    func testSavedTripMapLoadsOnlyWhenOpenedAndKeepsTheScheduleOnFailure() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", "en"]
        app.launchEnvironment = [
            "G2C_LIO_PREVIEW_TRIP": "__LIO_RECORDED_TRIP_FIXTURE__",
            "G2C_ACCEPTANCE_MAP_LOADING": "synthetic-delegate-failure"
        ]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.tabBars.buttons["Trips"].waitForExistence(timeout: 12))
        app.tabBars.buttons["Trips"].tap()
        let trip = app.buttons["Draft"]
        XCTAssertTrue(trip.waitForExistence(timeout: 8), app.debugDescription)
        trip.tap()
        let schedule = app.staticTexts["Date to be decided"]
        XCTAssertTrue(schedule.waitForExistence(timeout: 8))
        let map = app.buttons["lio.trip.recorded-map"]
        if !map.isHittable { app.swipeUp() }
        XCTAssertTrue(map.isHittable, app.debugDescription)
        let recordedFailure = app.staticTexts["lio.trip.recorded-map.unavailable"]
        XCTAssertFalse(recordedFailure.exists)
        XCTAssertTrue(app.staticTexts["lio.trip.route-map.unavailable"].exists)
        XCTAssertTrue(schedule.exists)
        map.tap()
        XCTAssertTrue(recordedFailure.waitForExistence(timeout: 8))
        XCTAssertTrue(schedule.exists)
    }

    func testHistoricalChatCardOpensTheCurrentSavedTrip() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", "--lio-stale-trip-acceptance",
                               "-cj.ui.language.v1", "en"]
        app.launchEnvironment = ["G2C_LIO_PREVIEW_TRIP": "__LIO_RECORDED_TRIP_FIXTURE__"]
        app.launch()
        defer { app.terminate() }

        let example = app.buttons["lio.example.0"]
        XCTAssertTrue(example.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        let viewTrip = app.buttons["lio.trip.show"]
        XCTAssertTrue(viewTrip.waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["Earlier plan"].exists)
        viewTrip.tap()
        XCTAssertTrue(app.staticTexts["Draft"].waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertTrue(app.staticTexts["Date to be decided"].exists)
        XCTAssertFalse(app.staticTexts["Earlier plan"].exists)
        XCTAssertFalse(app.staticTexts["Earlier stop"].exists)

        app.tabBars.buttons["Chat"].tap()
        XCTAssertTrue(viewTrip.waitForExistence(timeout: 8))
        viewTrip.tap()
        XCTAssertTrue(app.staticTexts["Trip unavailable"].waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertFalse(app.staticTexts["Date to be decided"].exists)
        XCTAssertFalse(app.staticTexts["Earlier stop"].exists)
    }

    private func exerciseTrip(_ language: String, clarification: String, trips: String, day: String, fixed: String,
                              largest: Bool = false, appearance: String = "light") throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launchArguments += ["-lio.ui.appearance.v1", appearance]
        if largest { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.1"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 1)
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
        let firstDay = app.buttons["lio.trip.day.1"]
        XCTAssertTrue(firstDay.waitForExistence(timeout: 6), app.debugDescription)
        XCTAssertTrue(firstDay.isSelected)
        XCTAssertTrue(app.staticTexts[fixed].waitForExistence(timeout: 6))
        app.buttons["lio.trip.day.2"].tap()
        XCTAssertFalse(app.staticTexts[fixed].exists)
        firstDay.tap()
        XCTAssertTrue(app.staticTexts[fixed].waitForExistence(timeout: 6))
        show.tap()

        XCTAssertTrue(app.navigationBars[trips].waitForExistence(timeout: 8))
        let chinese = language == "zh-Hans"
        let trip = app.buttons.containing(.staticText, identifier: chinese ? "北京三日行" : "Three days in Beijing").firstMatch
        XCTAssertTrue(trip.waitForExistence(timeout: 8), app.debugDescription)
        trip.tap()
        let routeMap = app.descendants(matching: .any).matching(identifier: "lio.trip.route-map").firstMatch
        XCTAssertTrue(routeMap.waitForExistence(timeout: 8), app.debugDescription)
        XCTAssertEqual(routeMap.label, language == "zh-Hans" ? "行程地图" : "Trip map")
        let hotel = app.staticTexts[fixed]
        if !hotel.isHittable { app.swipeUp() }
        XCTAssertTrue(hotel.waitForExistence(timeout: 8))
        let walk = app.buttons["lio.trip.focus.old-town-walk"]
        if !walk.isHittable { app.swipeDown() }
        XCTAssertTrue(walk.isHittable, app.debugDescription)
        walk.tap()
        XCTAssertEqual(routeMap.value as? String, walk.label)
        XCTAssertNotEqual(routeMap.value as? String, "old-town-walk")
        let second = app.buttons["lio.trip.select-day.2"]
        if !second.isHittable { app.swipeDown() }
        second.tap()
        XCTAssertTrue((routeMap.value as? String ?? "").isEmpty)
        XCTAssertTrue(app.buttons["lio.trip.focus.museum"].waitForExistence(timeout: 8))
        XCTAssertFalse(hotel.exists)
        XCTAssertTrue(app.buttons["lio.trip.focus.park"].exists)
        app.buttons["lio.trip.select-day.1"].tap()
        XCTAssertTrue(hotel.waitForExistence(timeout: 8))
        let fixedStatus = app.staticTexts[chinese ? "固定安排" : "Fixed plan"]
        if fixedStatus.frame.maxY > app.tabBars.firstMatch.frame.minY - 12 { app.swipeUp() }
        XCTAssertTrue(fixedStatus.isHittable)
        XCTAssertLessThanOrEqual(fixedStatus.frame.maxY, app.tabBars.firstMatch.frame.minY)
        try app.performAccessibilityAudit(for: .all)
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "trip-timeline-\(language)-\(appearance)-\(largest ? "largest" : "normal")"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testResendUsesTheSameQuestionAndQuotaStopsRetry() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", "--lio-resend-acceptance",
                               "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()

        let failure = app.staticTexts["lio.failure"]
        let resend = app.buttons["lio.resend"]
        let questions = app.textViews.matching(identifier: "lio.question")
        XCTAssertTrue(resend.waitForExistence(timeout: 8))
        XCTAssertTrue(resend.isHittable)
        XCTAssertEqual(failure.label, "消息没发出去。检查网络后，点感叹号重发。")
        XCTAssertEqual(questions.count, 1)
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")

        resend.tap()
        let quota = app.staticTexts.containing(NSPredicate(format: "label == %@", "今天的问题额度已用完，明天再来聊吧。"))
            .firstMatch
        XCTAssertTrue(quota.waitForExistence(timeout: 8))
        XCTAssertEqual(questions.count, 1)
        XCTAssertEqual(questions.firstMatch.value as? String, "在上海怎么坐地铁？")
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "2")
        XCTAssertFalse(resend.exists)
        XCTAssertFalse(app.buttons["lio.askAgain"].exists)
    }

    func testAcceptedFailureDescribesOnlyTheCurrentRequest() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for (scenario, english, chinese) in [
            ("--lio-accepted-failure-acceptance", "I couldn’t complete this request.", "这次没能完成你的请求。"),
            ("--lio-accepted-limit-acceptance", "Lio couldn’t finish this request within the current limit.", "这次没能在限额内答完。")
        ] {
            for language in ["en", "zh-Hans"] {
                app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", scenario,
                                       "-cj.ui.language.v1", language]
                app.launch()
                defer { app.terminate() }

                let example = app.buttons["lio.example.1"]
                XCTAssertTrue(example.waitForExistence(timeout: 12))
                enterSampleQuestion(in: app, index: 1)
                app.buttons["lio.send"].tap()
                let failure = app.staticTexts["lio.failure"]
                XCTAssertTrue(failure.waitForExistence(timeout: 8))
                XCTAssertEqual(failure.label, language == "en" ? english : chinese)
                XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")
                XCTAssertFalse(app.staticTexts["lio.answer"].exists)
                XCTAssertFalse(app.buttons["lio.source"].exists)
                XCTAssertFalse(app.staticTexts["Amap Weather"].exists)
                XCTAssertFalse(app.buttons["lio.resend"].exists)
                XCTAssertFalse(app.buttons["lio.askAgain"].exists)
                let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                capture.name = "Lio-final-failure-" + language + scenario
                capture.lifetime = .keepAlways
                add(capture)
            }
        }
    }

    func testTimelinePrefixAndForegroundReadKeepTheSameQuestion() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-timeline-acceptance", "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        let answer = app.staticTexts["lio.answer"]
        let step = app.buttons["Next timeline state"]
        let readCount = app.staticTexts["lio.fixture.read-count"]
        XCTAssertTrue(composer.waitForExistence(timeout: 12))
        composer.tap()
        composer.typeText("北京明天天气")
        app.buttons["lio.send"].tap()
        XCTAssertTrue(app.textViews["lio.question"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["Lio 正在回复…"].exists)

        step.tap()
        XCTAssertTrue(app.staticTexts["Lio 正在回复…"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["正在查天气…"].exists)
        XCTAssertFalse(answer.exists)

        step.tap()
        XCTAssertTrue(answer.waitForExistence(timeout: 8))
        XCTAssertEqual(answer.label, "北京明天")
        XCTAssertFalse(app.buttons["lio.source"].exists)

        step.tap()
        let finished = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label == %@", "北京明天有小雨。"), object: answer
        )
        XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 8), .completed)
        XCTAssertEqual(answer.label, "北京明天有小雨。")
        XCTAssertFalse(app.buttons["lio.source"].exists)
        XCTAssertFalse(app.staticTexts["演示天气预报"].exists)
        XCTAssertFalse(app.staticTexts["lio.progress"].exists)
        let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        capture.name = "Lio-answer-without-tools"
        capture.lifetime = .keepAlways
        add(capture)

        let before = try XCTUnwrap(Int(readCount.label))
        XCUIDevice.shared.press(.home)
        app.activate()
        let reread = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label != %@", String(before)), object: readCount
        )
        XCTAssertEqual(XCTWaiter.wait(for: [reread], timeout: 8), .completed)
        XCTAssertGreaterThan(try XCTUnwrap(Int(readCount.label)), before)
        XCTAssertEqual(app.textViews.matching(identifier: "lio.question").count, 1)
        XCTAssertEqual(answer.label, "北京明天有小雨。")
        XCTAssertEqual(app.staticTexts["lio.fixture.send-count"].label, "1")
    }

    func testUnsafeReplyIsWithheldWithoutExposingTools() {
        exerciseWithheldReply("--lio-display-guard")
    }

    func testMarkdownCannotExposeServiceTerms() {
        exerciseWithheldReply("--lio-display-guard-markdown")
        exerciseWithheldReply("--lio-display-guard-host")
        exerciseWithheldReply("--lio-display-guard-wrapped-host")
        exerciseWithheldReply("--lio-display-guard-thought")
        exerciseWithheldReply("--lio-display-guard-tool")
    }

    private func exerciseWithheldReply(_ fixture: String) {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", fixture, "-cj.ui.language.v1", "zh-Hans"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        XCTAssertTrue(app.staticTexts["lio.answer"].waitForExistence(timeout: 8))
        app.buttons["Next section"].tap()
        let withheld = app.staticTexts["lio.reply.unavailable"]
        XCTAssertTrue(withheld.waitForExistence(timeout: 8))
        XCTAssertEqual(withheld.label, "这条回答暂时无法显示。")
        XCTAssertFalse(app.staticTexts["lio.answer"].exists)
        XCTAssertFalse(app.buttons["lio.source"].exists)
    }

    func testFloatingControlsStayAccessibleInBothAppearancesAndLanguages() throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            for appearance in ["light", "dark"] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
                app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance",
                                       "-cj.ui.language.v1", language, "-lio.ui.appearance.v1", appearance]
                app.launch()
                XCTAssertTrue(app.staticTexts["An earlier reply."].waitForExistence(timeout: 12))
                let menu = app.buttons["lio.menu"]
                let newChat = app.buttons["lio.chat.newShortcut"]
                for button in [menu, newChat] {
                    XCTAssertTrue(button.isHittable)
                    XCTAssertGreaterThanOrEqual(button.frame.width, 44)
                    XCTAssertGreaterThanOrEqual(button.frame.height, 44)
                }
                try app.performAccessibilityAudit(for: .all)
                let image = XCTAttachment(screenshot: app.screenshot())
                image.name = "floating-controls-\(language)-\(appearance)"
                image.lifetime = .keepAlways
                add(image)
                newChat.tap()
                XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 8))
                XCTAssertFalse(app.staticTexts["An earlier reply."].exists)
                try app.performAccessibilityAudit(for: .all)
                let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
                composer.tap()
                let draft = language == "en" ? "My draft" : "我的草稿"
                composer.typeText(draft)
                XCTAssertEqual(composer.value as? String, draft)
                app.terminate()
            }
        }
    }

    func testTopControlsCenterLioAndStartANewChat() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-chat-history-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let oldReply = app.staticTexts["An earlier reply."]
        XCTAssertTrue(oldReply.waitForExistence(timeout: 8))
        let menu = app.buttons["lio.menu"]
        let name = app.staticTexts["lio.name"]
        let shortcut = app.buttons["lio.chat.newShortcut"]
        XCTAssertTrue(name.exists)
        XCTAssertEqual(name.label, "Lio")
        XCTAssertEqual(name.frame.midX, app.windows.firstMatch.frame.midX, accuracy: 2)
        XCTAssertLessThan(menu.frame.maxX, name.frame.minX)
        XCTAssertGreaterThan(shortcut.frame.minX, name.frame.maxX)
        XCTAssertEqual(menu.frame.midY, shortcut.frame.midY, accuracy: 1)
        XCTAssertEqual(shortcut.label, "New chat")
        // Audit only the top controls; other elements are covered by testEnglish/testChinese.
        let controls: Set<String> = ["lio.name", "lio.chat.newShortcut", "lio.menu"]
        try app.performAccessibilityAudit(for: [.contrast, .hitRegion]) { issue in
            !controls.contains(issue.element?.identifier ?? "")
        }

        XCTAssertTrue(shortcut.isEnabled)
        shortcut.tap()
        XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["lio.opening"].exists)
        XCTAssertFalse(oldReply.exists)
        XCTAssertFalse(app.textViews["lio.question"].exists)
    }

    func testJumpToLatestReturnsToTheNewestReply() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let jump = app.buttons["lio.jumpToLatest"]
        XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
        XCTAssertFalse(jump.exists)
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        let answers = app.staticTexts.matching(identifier: "lio.answer")
        XCTAssertTrue(answers.firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(jump.exists)
        app.buttons["Next section"].tap()
        let long = answers.containing(NSPredicate(format: "label CONTAINS %@", "Long section.")).firstMatch
        XCTAssertTrue(long.waitForExistence(timeout: 8))

        app.scrollViews.firstMatch.swipeDown()
        app.scrollViews.firstMatch.swipeDown()
        XCTAssertTrue(jump.waitForExistence(timeout: 4))
        XCTAssertEqual(jump.label, "Jump to latest")
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertLessThan(jump.frame.maxY, composer.frame.minY)
        XCTAssertGreaterThan(long.frame.maxY, composer.frame.minY)
        jump.tap()
        let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: jump)
        XCTAssertEqual(XCTWaiter.wait(for: [gone], timeout: 4), .completed)
        XCTAssertLessThanOrEqual(long.frame.maxY, composer.frame.minY)

        app.buttons["Next section"].tap()
        let finished = answers.containing(NSPredicate(format: "label CONTAINS %@", "End of the reply.")).firstMatch
        XCTAssertTrue(finished.waitForExistence(timeout: 8))
        XCTAssertLessThanOrEqual(finished.frame.maxY, composer.frame.minY)
    }

    func testLongPressOffersCopyOnMessages() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", "en", "-AppleLanguages", "(en)"]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()
        let answer = app.staticTexts["lio.answer"]
        XCTAssertTrue(answer.waitForExistence(timeout: 8))
        XCTAssertTrue(app.textViews["lio.question"].exists)
        answer.press(forDuration: 1.2)
        XCTAssertTrue(app.menuItems["Copy"].waitForExistence(timeout: 4), app.debugDescription)
    }

    func testLongReplyFollowsUntilTheReaderScrollsAway() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-scroll-acceptance", "-cj.ui.language.v1", "en"]
        app.launch()
        defer { app.terminate() }

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.waitForExistence(timeout: 12))
        enterSampleQuestion(in: app, index: 0)
        app.buttons["lio.send"].tap()

        let advance = app.buttons["Next section"]
        let answers = app.staticTexts.matching(identifier: "lio.answer")
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertTrue(answers.firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["lio.source"].exists)
        advance.tap()
        let long = answers.containing(NSPredicate(format: "label CONTAINS %@", "Long section.")).firstMatch
        XCTAssertTrue(long.waitForExistence(timeout: 8))
        XCTAssertLessThanOrEqual(long.frame.maxY, composer.frame.minY)
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)

        app.scrollViews.firstMatch.swipeDown()
        let readerPosition = long.frame.minY
        advance.tap()
        let finished = answers.containing(NSPredicate(format: "label CONTAINS %@", "End of the reply.")).firstMatch
        XCTAssertTrue(finished.waitForExistence(timeout: 8))
        XCTAssertEqual(finished.frame.minY, readerPosition, accuracy: 2)
        XCTAssertFalse(app.buttons["lio.source"].exists)
    }

    private func enterSampleQuestion(in app: XCUIApplication, index: Int) {
        let chinese = app.launchArguments.contains("zh-Hans")
        let questions = chinese
            ? ["在上海怎么坐地铁？", "帮我规划北京三天两晚的旅行。"]
            : ["How do I take the metro in Shanghai?", "Plan a three-day trip to Beijing."]
        app.buttons["lio.example.\(index)"].tap()
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        let starter = composer.value as? String ?? ""
        XCTAssertFalse(starter.isEmpty)
        XCTAssertFalse(app.textViews["lio.question"].exists)
        composer.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: starter.count) + questions[index])
        XCTAssertEqual(composer.value as? String, questions[index])
    }

    func testStartersOnlyFillTheComposerInBothLanguages() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for language in ["en", "zh-Hans"] {
            app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
            app.launch()
            let chinese = language == "zh-Hans"
            let labels = chinese ? ["天气", "景点", "交通", "行程"] : ["Weather", "Sights", "Transport", "Trips"]
            let prefixes = chinese ? ["天气：", "景点：", "交通：", "规划行程："]
                : ["Weather: ", "Sights: ", "Transport: ", "Plan a trip: "]
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(composer.waitForExistence(timeout: 12))
            let first = app.buttons["lio.example.0"]
            let last = app.buttons["lio.example.3"]
            XCTAssertTrue(first.isHittable)
            XCTAssertTrue(last.isHittable)
            XCTAssertEqual(first.frame.midY, last.frame.midY, accuracy: 1)
            let capture = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            capture.name = "Lio-starters-" + language
            capture.lifetime = .keepAlways
            add(capture)
            for index in 0..<4 {
                let button = app.buttons["lio.example.\(index)"]
                XCTAssertEqual(button.label, labels[index])
                button.tap()
                XCTAssertEqual(composer.value as? String, prefixes[index])
                XCTAssertFalse(app.textViews["lio.question"].exists)
                XCTAssertFalse(app.staticTexts["lio.answer"].exists)
                XCTAssertTrue(button.exists)
            }
            composer.typeText(chinese ? "北京三天" : "three days in Beijing")
            app.buttons["lio.send"].tap()
            XCTAssertTrue(app.textViews["lio.question"].waitForExistence(timeout: 8))
            XCTAssertEqual(app.textViews["lio.question"].value as? String,
                           prefixes[3] + (chinese ? "北京三天" : "three days in Beijing"))
            XCTAssertFalse(first.exists)
            XCTAssertFalse(last.exists)
            app.terminate()
        }
    }

    func testRememberedFeedbackStaysWithItsReplyAndFades() throws {
        try exerciseInlineMemoryFeedback(changed: false)
    }

    func testChangedMemoryFeedbackStaysWithItsReply() throws {
        try exerciseInlineMemoryFeedback(changed: true)
    }

    func testLargestMemoryConfirmationKeepsBothActionsReachable() {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "-cj.ui.language.v1", language,
                                   "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
            app.launch()
            XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
            let input = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            input.tap(); input.typeText(language == "en" ? "I prefer quiet hotels" : "我喜欢安静的酒店")
            app.buttons["lio.send"].tap()
            let remember = app.buttons["lio.memory.remember"]
            let dismiss = app.buttons["lio.memory.dismiss"]
            XCTAssertTrue(remember.waitForExistence(timeout: 10))
            let jump = app.buttons["lio.jumpToLatest"]
            if jump.waitForExistence(timeout: 2), jump.isHittable { jump.tap() }
            for _ in 0..<8 {
                if dismiss.isHittable && dismiss.frame.maxY <= input.frame.minY { break }
                app.scrollViews.firstMatch.swipeUp()
            }
            XCTAssertTrue(remember.isHittable, app.debugDescription)
            XCTAssertTrue(dismiss.isHittable, app.debugDescription)
            XCTAssertLessThanOrEqual(remember.frame.maxY, dismiss.frame.minY)
            XCTAssertLessThanOrEqual(dismiss.frame.maxY, input.frame.minY)
            XCTAssertGreaterThanOrEqual(remember.frame.width, 44)
            XCTAssertGreaterThanOrEqual(remember.frame.height, 44)
            XCTAssertGreaterThanOrEqual(dismiss.frame.width, 44)
            XCTAssertGreaterThanOrEqual(dismiss.frame.height, 44)
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = language + "-largest-memory-confirmation"
            shot.lifetime = .keepAlways
            add(shot)
            app.terminate()
        }
    }

    private func exerciseInlineMemoryFeedback(changed: Bool) throws {
        continueAfterFailure = false
        for language in ["en", "zh-Hans"] {
            let english = language == "en"
            let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
            app.launchArguments = ["--lio-preview", "--lio-journey-acceptance", "-cj.ui.language.v1", language]
            if changed { app.launchArguments.append("--lio-memory-changed-acceptance") }
            app.launch()
            XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 12))
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            composer.tap(); composer.typeText(english ? "I prefer quiet hotels" : "我喜欢安静的酒店")
            app.buttons["lio.send"].tap()
            let remember = app.buttons["lio.memory.remember"]
            XCTAssertTrue(remember.waitForExistence(timeout: 10))
            XCTAssertFalse(app.staticTexts[english ? "Review the request ID" : "核实 operation_id"].exists)
            try auditMemoryConfirmation(in: app)
            let followUp = english ? "Any other hotel advice?" : "还有其他酒店建议吗？"
            composer.tap(); composer.typeText(followUp); app.buttons["lio.send"].tap()
            let question = app.textViews.matching(identifier: "lio.question")
                .matching(NSPredicate(format: "value == %@", followUp)).firstMatch
            XCTAssertTrue(question.waitForExistence(timeout: 8))
            XCTAssertEqual(question.value as? String, followUp)
            remember.tap()
            let status = app.staticTexts[changed
                ? (english ? "That suggestion changed." : "这条建议已有变化。")
                : (english ? "Remembered" : "已记住")]
            XCTAssertTrue(status.waitForExistence(timeout: 10), app.debugDescription)
            XCTAssertLessThan(status.frame.maxY, question.frame.minY)
            XCTAssertFalse(remember.exists)
            if !changed {
                let gone = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: status)
                XCTAssertEqual(XCTWaiter.wait(for: [gone], timeout: 5), .completed)
                XCTAssertFalse(remember.exists)
            }
            app.terminate()
        }
    }

    private func auditMemoryConfirmation(in app: XCUIApplication) throws {
        try app.performAccessibilityAudit(for: .all) { issue in
            let detail = XCTAttachment(string: String(describing: issue.auditType) + "\n" +
                                       (issue.element?.debugDescription ?? "No element supplied by audit"))
            detail.name = "Card and memory AX issue"
            detail.lifetime = .keepAlways
            self.add(detail)
            return false
        }
    }

    private func exercise(_ language: String, question: String) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", language]
        app.launch()
        defer { app.terminate() }

        XCTAssertTrue(app.buttons["lio.menu"].waitForExistence(timeout: 12))
        XCTAssertTrue(app.staticTexts["Lio"].exists)
        let greeting = app.staticTexts["lio.opening"]
        XCTAssertTrue(greeting.exists)
        XCTAssertEqual(greeting.label, language == "en" ? "Hi, I'm Lio. Tell me the city, how many days you have and what you enjoy, and I'll plan where to go and how to get around each day. Where are you headed?"
                       : "你好，我是 Lio。告诉我城市、天数和喜好，我帮你排好每天去哪、怎么走。这次想去哪儿？")
        XCTAssertFalse(app.textViews["lio.question"].exists)
        XCTAssertFalse(app.navigationBars.firstMatch.exists)
        XCTAssertTrue(app.tabBars.buttons[language == "en" ? "Trips" : "行程"].exists)
        XCTAssertFalse(app.buttons["lio.send"].isEnabled)

        let sample = app.buttons["lio.example.0"]
        XCTAssertTrue(sample.isHittable)
        try app.performAccessibilityAudit(for: .all)

        enterSampleQuestion(in: app, index: 0)
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        XCTAssertEqual(composer.value as? String, question)
        XCTAssertFalse(app.textViews["lio.question"].exists)
        XCTAssertTrue(app.buttons["lio.send"].isEnabled)
        app.buttons["lio.send"].tap()

        let sentQuestion = app.textViews["lio.question"]
        let answer = app.staticTexts["lio.answer"]
        XCTAssertTrue(sentQuestion.waitForExistence(timeout: 8))
        XCTAssertTrue(answer.waitForExistence(timeout: 8))
        XCTAssertLessThan(answer.frame.minX, sentQuestion.frame.minX)
        XCTAssertGreaterThanOrEqual(answer.frame.minY, sentQuestion.frame.maxY)
        XCTAssertFalse(app.buttons["lio.source"].exists)
        XCTAssertFalse(app.staticTexts["lio.progress"].exists)
        XCTAssertFalse(app.navigationBars.firstMatch.exists)
        XCTAssertFalse(app.links.firstMatch.exists)
    }
    func testExplorationQuestionsEnglish() throws { try exerciseQuestionControls(chinese: false) }
    func testExplorationQuestionsChinese() throws { try exerciseQuestionControls(chinese: true) }

    private func exerciseQuestionControls(chinese: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for dark in [false, true] {
            app.launchArguments = ["--lio-preview", "--lio-question-controls-acceptance", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", dark ? "dark" : "light"]
            app.launch()
            let submit = app.buttons["lio.questions.continue"]
            let history = app.buttons["lio.questions.one.interests.history"]
            let food = app.buttons["lio.questions.one.interests.food"]
            let slow = app.buttons["lio.questions.one.pace.slow"]
            let active = app.buttons["lio.questions.one.pace.active"]
            XCTAssertTrue(submit.waitForExistence(timeout: 10))
            XCTAssertEqual(submit.label, chinese ? "好了，继续" : "Done, continue")
            XCTAssertFalse(submit.isEnabled)
            food.tap()
            history.tap()
            XCTAssertTrue(food.isSelected)
            XCTAssertTrue(history.isSelected)
            XCTAssertEqual(app.staticTexts["fixture.send-count"].label, "0")
            app.buttons["fixture.refresh"].tap()
            XCTAssertTrue(food.isSelected)
            XCTAssertTrue(history.isSelected)
            try app.performAccessibilityAudit(for: .all)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "questions-\(chinese ? "zh" : "en")-\(dark ? "dark" : "light")"
            image.lifetime = .keepAlways
            add(image)
            submit.tap()
            XCTAssertEqual(app.staticTexts["fixture.send-count"].label, "1")
            XCTAssertEqual(app.staticTexts["fixture.sent"].label, chinese ? "兴趣：历史文化\n兴趣：当地美食" : "Interests: History\nInterests: Food")
            slow.tap()
            active.tap()
            XCTAssertFalse(slow.isSelected)
            XCTAssertTrue(active.isSelected)
            history.tap()
            submit.tap()
            XCTAssertEqual(app.staticTexts["fixture.send-count"].label, "2")
            XCTAssertEqual(app.staticTexts["fixture.sent"].label, chinese ? "兴趣：当地美食\n节奏：充实些" : "Interests: Food\nPace: Active")
            app.buttons["fixture.read-only"].tap()
            XCTAssertFalse(submit.isEnabled)
            XCTAssertFalse(food.isEnabled)
            XCTAssertEqual(app.staticTexts["fixture.send-count"].label, "2")
            app.terminate()
        }
    }

    func testExplorationQuestionsLargeText() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for chinese in [false, true] {
            app.launchArguments = ["--lio-preview", "--lio-question-controls-acceptance", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", "light", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
            app.launch()
            let history = app.buttons["lio.questions.one.interests.history"]
            XCTAssertTrue(history.waitForExistence(timeout: 10))
            XCTAssertGreaterThanOrEqual(history.frame.height, 44)
            let food = app.buttons["lio.questions.one.interests.food"]
            XCTAssertGreaterThanOrEqual(food.frame.minY, history.frame.maxY)
            history.tap()
            let submit = app.buttons["lio.questions.continue"]
            for _ in 0..<4 {
                if submit.isHittable { break }
                app.swipeUp()
            }
            XCTAssertTrue(submit.isHittable)
            XCTAssertTrue(submit.isEnabled)
            try app.performAccessibilityAudit(for: .all)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "questions-large-\(chinese ? "zh" : "en")"
            image.lifetime = .keepAlways
            add(image)
            app.terminate()
        }
    }
    func testExplorationHomeProgressInBothLanguages() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for chinese in [false, true] {
            app.launchArguments = ["--lio-preview", "--lio-exploration-home-acceptance", "--lio-home-progress-acceptance",
                                   "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", "light"]
            app.launch()
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(composer.waitForExistence(timeout: 10))
            composer.tap()
            composer.typeText(chinese ? "北京三天" : "Beijing for three days")
            app.buttons["lio.send"].tap()
            let indicator = app.staticTexts["lio.progress"]
            func expectProgress(_ text: String) {
                let expected = NSPredicate(format: "value == %@", text)
                XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: expected, object: indicator)],
                                              timeout: 12), .completed)
                let image = XCTAttachment(screenshot: app.screenshot())
                image.name = "home-progress-\(chinese ? "zh" : "en")-\(text)"
                image.lifetime = .keepAlways
                add(image)
            }
            expectProgress(chinese ? "正在比较酒店的位置" : "Comparing hotel locations")
            expectProgress(chinese ? "开始安排三天行程" : "Starting your three-day plan")
            let reply = app.descendants(matching: .any).matching(identifier: "lio.segment.0").firstMatch
            XCTAssertTrue(reply.waitForExistence(timeout: 20))
            XCTAssertTrue(indicator.waitForNonExistence(timeout: 5))
            let second = app.descendants(matching: .any).matching(identifier: "lio.segment.1").firstMatch
            var previousFrames: [CGRect]?
            let settled = NSPredicate { _, _ in
                guard reply.exists, second.exists else { previousFrames = nil; return false }
                let frames = [reply.frame, second.frame]
                let viewport = app.scrollViews.firstMatch.frame
                guard frames.allSatisfy({ viewport.contains($0) }) else { previousFrames = nil; return false }
                defer { previousFrames = frames }
                return previousFrames == frames
            }
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: settled, object: nil)], timeout: 12), .completed)
            try app.performAccessibilityAudit(for: .all)
            showLioMe(app)
            let stored = app.staticTexts["fixture.finished-timings"]
            XCTAssertTrue(stored.waitForExistence(timeout: 5))
            XCTAssertEqual(stored.label, "1")
            XCTAssertEqual(stored.value as? String, "complete")
            app.terminate()
        }
    }

    func testNativeQuestionKeepsSelectionAndOpeningCopies() throws {
        continueAfterFailure = false
        let clipboard = LioClipboardSnapshot()
        addTeardownBlock { await clipboard.restore() }
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        app.launchArguments = ["--lio-preview", "--lio-exploration-home-acceptance", "--lio-home-legacy1-acceptance",
                               "-cj.ui.language.v1", "en", "-lio.ui.appearance.v1", "light"]
        app.launch()
        addTeardownBlock { await MainActor.run { app.terminate() } }
        let opening = app.staticTexts["lio.opening"]
        XCTAssertTrue(opening.waitForExistence(timeout: 12))
        let openingText = opening.label
        opening.press(forDuration: 1.2)
        let copyOpening = app.buttons["lio.copy.opening"]
        XCTAssertTrue(copyOpening.waitForExistence(timeout: 5))
        copyOpening.tap()
        XCTAssertTrue(copyOpening.waitForNonExistence(timeout: 5))
        func copiedDigest() -> String? {
            showLioMe(app)
            let probe = app.buttons["fixture.clipboard.probe"]
            XCTAssertTrue(probe.waitForExistence(timeout: 5))
            probe.tap()
            let digest = app.staticTexts["fixture.clipboard.digest"].value as? String
            showLioChat(app)
            XCTAssertTrue(probe.waitForNonExistence(timeout: 5))
            return digest
        }
        func digest(_ text: String) -> String {
            SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        XCTAssertEqual(copiedDigest(), digest(openingText))
        let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
        composer.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        composer.typeText("Slow travel please")
        app.buttons["lio.send"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "lio.answer").firstMatch.waitForExistence(timeout: 12))
        let question = app.textViews["lio.question"]
        for _ in 0..<8 {
            if question.exists && question.isHittable && app.scrollViews.firstMatch.frame.contains(question.frame) { break }
            app.swipeDown()
        }
        XCTAssertTrue(question.isHittable)
        XCTAssertEqual(question.value as? String, "Slow travel please")
        question.press(forDuration: 1.2)
        let copy = app.descendants(matching: .any).matching(NSPredicate(format: "label IN %@", ["Copy", "拷贝", "复制"])).firstMatch
        XCTAssertTrue(copy.waitForExistence(timeout: 5), app.debugDescription)
        XCTAssertTrue(copy.isEnabled)
        copy.tap()
        XCTAssertTrue(copy.waitForNonExistence(timeout: 5))
        let selected = copiedDigest()
        XCTAssertTrue(["Slow", "travel", "please"].map(digest).contains { $0 == selected }, "Copy must retain selection of a fragment")
    }

    func testOrdinaryHomeLegacyMessagesEnglish() throws { try exerciseOrdinaryHomeLegacy(chinese: false) }
    func testOrdinaryHomeLegacyMessagesChinese() throws { try exerciseOrdinaryHomeLegacy(chinese: true) }

    private func exerciseOrdinaryHomeLegacy(chinese: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for version in [1, 2] {
            app.launchArguments = ["--lio-preview", "--lio-exploration-home-acceptance",
                                   "--lio-home-legacy\(version)-acceptance", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                   "-lio.ui.appearance.v1", "light"]
            app.launch()
            defer { app.terminate() }
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(composer.waitForExistence(timeout: 12), app.debugDescription)
            composer.tap(); composer.typeText("Some travel ideas")
            app.buttons["lio.send"].tap()
            let answer = app.descendants(matching: .any).matching(identifier: "lio.answer").firstMatch
            XCTAssertTrue(answer.waitForExistence(timeout: 12), app.debugDescription)
            let expected = chinese ? "日期可以之后再定。" : "Dates can stay open."
            let complete = NSPredicate { _, _ in
                answer.label.contains(expected) || answer.descendants(matching: .staticText)
                    .allElementsBoundByIndex.contains { $0.label.contains(expected) }
            }
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: complete, object: nil)], timeout: 12), .completed)
            let visible = answer.label + answer.descendants(matching: .staticText).allElementsBoundByIndex.map(\.label).joined(separator: "\n")
            XCTAssertTrue(visible.contains(chinese ? "之前的回答" : "Earlier reply"))
            XCTAssertTrue(visible.contains(chinese ? "大致安排" : "outline"))
            XCTAssertFalse(visible.contains("##")); XCTAssertFalse(visible.contains("**"))
            XCTAssertEqual(app.textViews.matching(identifier: "lio.question").count, 1)
            XCTAssertFalse(app.buttons["lio.questions.continue"].exists)
            XCTAssertFalse(app.descendants(matching: .any).matching(identifier: "lio.segment.0").firstMatch.exists)
            try app.performAccessibilityAudit(for: .all)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "ordinary-legacy\(version)-\(chinese ? "zh" : "en")"; image.lifetime = .keepAlways; add(image)
            app.terminate()
        }
    }

    func testExplorationHomeEnglish() throws { try exerciseExplorationHome(chinese: false) }
    func testExplorationHomeChinese() throws { try exerciseExplorationHome(chinese: true) }

    /// #1453: a plan summary in a v4 reply opens the day-by-day page; it can be saved, shown in Trips, changed per day
    /// through the chat and removed again.
    func testPlanCardOpensTheDayByDayPageChinese() throws { try exercisePlanCard(chinese: true) }
    func testPlanCardOpensTheDayByDayPageEnglish() throws { try exercisePlanCard(chinese: false) }

    private func exercisePlanCard(chinese: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
        func reveal(_ target: XCUIElement) {
            for _ in 0..<8 where !(target.exists && target.isHittable) { app.swipeUp() }
            XCTAssertTrue(target.isHittable, app.debugDescription)
        }
        do {
            app.launchArguments = ["--lio-preview", "--lio-exploration-home-acceptance", "--lio-home-plan-acceptance",
                                   "-cj.ui.language.v1", chinese ? "zh-Hans" : "en", "-lio.ui.appearance.v1", "light"]
            app.launch()
            let composer = element("lio.composer")
            XCTAssertTrue(composer.waitForExistence(timeout: 12), app.debugDescription)
            composer.tap(); composer.typeText(chinese ? "帮我规划三天北京自由行" : "Plan three days in Beijing")
            app.buttons["lio.send"].tap()

            let open = app.buttons["lio.plan.open"]
            XCTAssertTrue(open.waitForExistence(timeout: 12), app.debugDescription)
            reveal(open)
            XCTAssertTrue(element("lio.plan.card").staticTexts[chinese ? "北京三日行" : "Three days in Beijing"].exists)
            XCTAssertTrue(element("lio.plan.card").staticTexts[chinese ? "3 天 · 4 个地点" : "3 days · 4 stops"].exists)
            open.tap()

            let save = app.buttons["lio.plan.save"]
            XCTAssertTrue(save.waitForExistence(timeout: 5), app.debugDescription)
            XCTAssertTrue(app.staticTexts[chinese ? "故宫博物院" : "Palace Museum"].exists)
            XCTAssertTrue(app.staticTexts[chinese ? "3 天 · 4 个地点 · 日期待定" : "3 days · 4 stops · dates not set"].exists)
            XCTAssertTrue(app.buttons["lio.plan.share"].exists)
            // A summary has no confirmed address: no taxi, map or driver actions, and no day map.
            XCTAssertFalse(app.staticTexts[chinese ? "司机卡" : "Driver"].exists)
            XCTAssertFalse(app.maps.firstMatch.exists)
            try app.performAccessibilityAudit(for: .all) { issue in
                let detail = XCTAttachment(string: issue.compactDescription + "\n" + issue.detailedDescription + "\n"
                    + (issue.element?.debugDescription ?? "No element supplied"))
                detail.name = "plan-page-audit"; detail.lifetime = .keepAlways; self.add(detail)
                return false
            }
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "plan-day1-\(chinese ? "zh" : "en")"; shot.lifetime = .keepAlways; add(shot)

            save.tap()
            XCTAssertTrue(element("lio.plan.saved").waitForExistence(timeout: 5), app.debugDescription)
            let dayThree = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", chinese ? "第 3 天" : "Day 3")).firstMatch
            dayThree.tap()
            XCTAssertTrue(element("lio.plan.empty-day").waitForExistence(timeout: 5), app.debugDescription)
            let dayOne = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", chinese ? "第 1 天" : "Day 1")).firstMatch
            dayOne.tap()
            let adjust = app.buttons["lio.plan.adjust-day"]
            reveal(adjust); adjust.tap()
            XCTAssertTrue(save.waitForNonExistence(timeout: 5))
            XCTAssertTrue(element("lio.plan.saved").waitForNonExistence(timeout: 5))
            XCTAssertEqual(composer.value as? String,
                           chinese ? "调整「北京三日行」第 1 天：" : "Change day 1 of “Three days in Beijing”: ")

            showLioTab(app, ["Trips", "行程"])
            let row = element("lio.plan.saved-row")
            XCTAssertTrue(row.waitForExistence(timeout: 5), app.debugDescription)
            row.tap()
            XCTAssertTrue(element("lio.plan.saved").waitForExistence(timeout: 5), app.debugDescription)
            app.buttons["lio.plan.done"].tap()
            XCTAssertTrue(element("lio.plan.saved").waitForNonExistence(timeout: 5))
            // From Trips, changing a day returns to the chat with the text ready; the earlier draft stays.
            row.tap()
            let adjustFromTrips = app.buttons["lio.plan.adjust-day"]
            reveal(adjustFromTrips); adjustFromTrips.tap()
            XCTAssertTrue(composer.waitForExistence(timeout: 5))
            XCTAssertTrue(element("lio.plan.saved").waitForNonExistence(timeout: 5))
            XCTAssertEqual(composer.value as? String,
                           chinese ? "调整「北京三日行」第 1 天：" : "Change day 1 of “Three days in Beijing”: ")
            showLioTab(app, ["Trips", "行程"])
            XCTAssertTrue(row.waitForExistence(timeout: 5), app.debugDescription)
            row.press(forDuration: 1.2)
            let remove = app.buttons[chinese ? "从行程中移除" : "Remove from Trips"]
            XCTAssertTrue(remove.waitForExistence(timeout: 5), app.debugDescription)
            remove.tap()
            XCTAssertTrue(row.waitForNonExistence(timeout: 5))
            app.terminate()
        }
    }

    private func exerciseExplorationHome(chinese: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        func ready(_ element: XCUIElement) {
            var previousFrame: CGRect?
            let settled = NSPredicate { _, _ in
                guard element.exists, element.isEnabled, element.isHittable else {
                    previousFrame = nil
                    return false
                }
                let frame = element.frame
                defer { previousFrame = frame }
                return previousFrame == frame
            }
            let condition = XCTNSPredicateExpectation(predicate: settled, object: nil)
            XCTAssertEqual(XCTWaiter.wait(for: [condition], timeout: 15), .completed)
        }
        func audit() throws {
            try app.performAccessibilityAudit(for: .all) { issue in
                let detail = XCTAttachment(string: issue.compactDescription + "\n" + issue.detailedDescription + "\n"
                    + (issue.element?.debugDescription ?? "No element supplied") + "\n" + app.debugDescription)
                detail.name = "exploration-home-audit"
                detail.lifetime = .keepAlways
                self.add(detail)
                return false
            }
        }
        func reveal(_ element: XCUIElement) {
            for _ in 0..<8 {
                if element.exists && element.isHittable && app.scrollViews.firstMatch.frame.contains(element.frame) {
                    ready(element)
                    if app.scrollViews.firstMatch.frame.contains(element.frame) { return }
                }
                if element.exists && element.frame.midY < app.frame.midY { app.swipeDown() }
                else { app.swipeUp() }
            }
            XCTAssertTrue(element.isHittable, app.debugDescription)
            XCTAssertTrue(app.scrollViews.firstMatch.frame.contains(element.frame), app.debugDescription)
        }
        func count(_ expected: Int, last: String? = nil) throws -> String {
            let menu = app.buttons["lio.menu"]
            ready(menu)
            showLioMe(app)
            let value = app.staticTexts["fixture.send-count"]
            XCTAssertTrue(value.waitForExistence(timeout: 5))
            XCTAssertEqual(value.label, String(expected))
            let messageID = value.value as! String
            XCTAssertFalse(messageID.isEmpty)
            if let last { XCTAssertEqual(app.staticTexts["fixture.last-text"].label, last) }
            XCTAssertEqual(app.staticTexts["fixture.finished-timings"].label, String(expected))
            XCTAssertEqual(app.staticTexts["fixture.finished-timings"].value as? String, "complete")
            // Before #1452 this audit covered the chat menu sheet, which only held these fixture rows. That sheet is
            // gone; the rows sit in the Me tab, whose audit is #1496. The chat page is audited below without any
            // tolerance. An audit right after switching tabs reported contrast on settled text (#1501), so none here.
            showLioChat(app)
            XCTAssertTrue(value.waitForNonExistence(timeout: 5))
            ready(menu)
            return "lio.exploration." + messageID
        }
        func reply(_ id: String) -> XCUIElement {
            app.descendants(matching: .any).matching(identifier: id).firstMatch
        }
        func showPrevious(_ element: XCUIElement) {
            for _ in 0..<8 {
                if element.exists { break }
                app.swipeDown()
            }
            XCTAssertTrue(element.exists, app.debugDescription)
        }
        for appearance in ["light", "dark"] {
            app.launchArguments = ["--lio-preview", "--lio-exploration-home-acceptance",
                                   "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                                   "-lio.ui.appearance.v1", appearance]
            app.launch()
            let composer = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
            XCTAssertTrue(composer.waitForExistence(timeout: 12), app.debugDescription)
            composer.tap(); composer.typeText("I would like some travel ideas")
            app.buttons["lio.send"].tap()
            let first = app.descendants(matching: .any).matching(identifier: "lio.segment.0").firstMatch
            XCTAssertTrue(first.waitForExistence(timeout: 12), app.debugDescription)
            let second = app.descendants(matching: .any).matching(identifier: "lio.segment.1").firstMatch
            XCTAssertLessThan(first.frame.minY, second.frame.minY)
            XCTAssertFalse(app.buttons.matching(NSPredicate(format: "identifier CONTAINS %@", "interests.other")).firstMatch.exists)
            let nature = app.buttons.matching(NSPredicate(format: "identifier ENDSWITH %@", ".interests.nature")).firstMatch
            let history = app.buttons.matching(NSPredicate(format: "identifier ENDSWITH %@", ".interests.history")).firstMatch
            reveal(nature); nature.tap(); reveal(history); history.tap()
            XCTAssertTrue(nature.isSelected && history.isSelected)
            let firstID = try count(1)
            XCTAssertTrue(nature.isSelected && history.isSelected)
            let firstProfile = reply(firstID).buttons["lio.profile.pace"]
            showPrevious(firstProfile)
            reveal(firstProfile)
            XCTAssertEqual(firstProfile.label, chinese ? "慢慢逛" : "An easy pace")
            XCTAssertEqual(firstProfile.value as? String, chinese ? "我的理解" : "My understanding")
            let submit = app.buttons["lio.questions.continue"]
            reveal(submit)
            try audit()
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "native-home-\(chinese ? "zh" : "en")-\(appearance)"
            shot.lifetime = .keepAlways; add(shot)
            submit.tap()
            let joint = chinese ? "兴趣：历史\n兴趣：自然" : "Interests: History\nInterests: Nature"
            let secondID = try count(2, last: joint)
            XCTAssertTrue(reply(secondID).waitForExistence(timeout: 12))
            let earlierProfile = reply(firstID).buttons["lio.profile.pace"]
            showPrevious(earlierProfile)
            XCTAssertFalse(earlierProfile.isEnabled)
            let profile = reply(secondID).buttons["lio.profile.pace"]
            reveal(profile); profile.tap()
            let field = app.descendants(matching: .any).matching(identifier: "lio.profile.edit.text").firstMatch
            XCTAssertTrue(field.waitForExistence(timeout: 5))
            field.tap()
            let previous = field.value as! String
            let change = chinese ? "节奏改为轻松" : "Prefer a relaxed pace"
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: previous.count) + change)
            try audit()
            XCUIDevice.shared.press(.home); app.activate()
            XCTAssertEqual(field.value as? String, change)
            ready(app.buttons["lio.profile.edit.send"])
            app.buttons["lio.profile.edit.send"].tap()
            XCTAssertTrue(field.waitForNonExistence(timeout: 5))
            let thirdID = try count(3, last: change)
            XCTAssertTrue(reply(thirdID).waitForExistence(timeout: 12))
            let earlierExit = reply(firstID).buttons["lio.exit.plan_now"]
            showPrevious(earlierExit)
            XCTAssertFalse(earlierExit.isEnabled)
            let exit = reply(thirdID).buttons["lio.exit.plan_now"]
            reveal(exit); ready(exit); exit.tap()
            let fourthID = try count(4, last: chinese ? "直接出方案" : "Make a plan now")
            XCTAssertTrue(reply(fourthID).waitForExistence(timeout: 12))
            app.terminate()
        }
    }

    func testExplorationReplyEnglish() throws { try exerciseExplorationReply(chinese: false) }
    func testExplorationReplyChinese() throws { try exerciseExplorationReply(chinese: true) }

    private func showExplorationReplyControl(_ element: XCUIElement, in app: XCUIApplication, down: Bool) {
        for _ in 0..<6 {
            if element.isHittable { return }
            if down { app.swipeUp() } else { app.swipeDown() }
        }
    }

    private func exerciseExplorationReply(chinese: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for dark in [false, true] {
            launchExplorationReply(app, chinese: chinese, dark: dark)
            let first = app.descendants(matching: .any).matching(identifier: "lio.segment.0").firstMatch
            let second = app.descendants(matching: .any).matching(identifier: "lio.segment.1").firstMatch
            XCTAssertTrue(first.waitForExistence(timeout: 10))
            XCTAssertLessThan(first.frame.minY, second.frame.minY)
            XCTAssertFalse(app.staticTexts["Combined answer for an older reader"].exists)
            let history = app.buttons["lio.questions.sample.interests.history"]
            showExplorationReplyControl(history, in: app, down: true)
            history.tap()
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "0")
            let submit = app.buttons["lio.questions.continue"]
            showExplorationReplyControl(submit, in: app, down: true)
            submit.tap()
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "1")
            XCTAssertEqual(app.staticTexts["fixture.sent"].label, chinese ? "喜欢历史文化" : "I enjoy history")
            let refresh = app.buttons["fixture.refresh"]
            showExplorationReplyControl(refresh, in: app, down: true)
            refresh.tap()
            XCTAssertEqual(app.descendants(matching: .any).matching(identifier: "lio.notice.weather-day-1").count, 1)
            XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "lio.segment.2").firstMatch.exists)
            XCTAssertTrue(history.isSelected)
            let profile = app.buttons["lio.profile.pace"]
            showExplorationReplyControl(profile, in: app, down: false)
            profile.tap()
            let sendControl = app.buttons["lio.profile.edit.send"]
            XCTAssertTrue(sendControl.waitForExistence(timeout: 5))
            XCTAssertGreaterThanOrEqual(sendControl.frame.height, 44)
            let field = app.descendants(matching: .any).matching(identifier: "lio.profile.edit.text").firstMatch
            XCTAssertTrue(field.waitForExistence(timeout: 5))
            field.tap()
            let old = field.value as! String
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + (chinese ? "节奏改为轻松" : "Pace: relaxed"))
            try app.performAccessibilityAudit(for: .all)
            let sheet = XCTAttachment(screenshot: app.screenshot())
            sheet.name = "profile-edit-\(chinese ? "zh" : "en")-\(dark ? "dark" : "light")"
            sheet.lifetime = .keepAlways
            add(sheet)
            app.buttons["lio.profile.edit.send"].tap()
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "2")
            XCTAssertEqual(app.staticTexts["fixture.sent"].label, chinese ? "节奏改为轻松" : "Pace: relaxed")
            let plan = app.buttons["lio.exit.plan_now"]
            showExplorationReplyControl(plan, in: app, down: true)
            XCTAssertGreaterThanOrEqual(plan.frame.height, 44)
            let sourceAction = app.descendants(matching: .any).matching(identifier: "lio.notice.source.weather-day-1").firstMatch
            XCTAssertFalse(sourceAction.exists, "A source row should not take up space in the reply")
            plan.tap()
            XCTAssertFalse(plan.exists)
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "3")
            XCTAssertEqual(app.staticTexts["fixture.sent"].label, chinese ? "直接给我一个方案。" : "Please make a plan now.")
            try app.performAccessibilityAudit(for: .all)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = "exploration-\(chinese ? "zh" : "en")-\(dark ? "dark" : "light")"
            image.lifetime = .keepAlways
            add(image)
            // Verify the context menu after the original reply audit and screenshot.
            let notice = app.descendants(matching: .any).matching(identifier: "lio.notice.weather-day-1").firstMatch
            showExplorationReplyControl(notice, in: app, down: false)
            XCTAssertTrue(notice.isHittable)
            notice.press(forDuration: 1)
            XCTAssertTrue(sourceAction.waitForExistence(timeout: 5), "The original source remains available from the reminder")
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.08)).tap()
            let readOnly = app.buttons["fixture.read-only"]
            showExplorationReplyControl(readOnly, in: app, down: true)
            readOnly.tap()
            XCTAssertFalse(plan.exists)
            XCTAssertFalse(submit.isEnabled)
            showExplorationReplyControl(profile, in: app, down: false)
            XCTAssertTrue(profile.exists)
            XCTAssertFalse(profile.isEnabled)
            app.terminate()
        }
    }

    func testExplorationReadOnlyDisablesUnconsumedExitInBothLanguages() {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for chinese in [false, true] {
            launchExplorationReply(app, chinese: chinese)
            let readOnly = app.buttons["fixture.read-only"]
            showExplorationReplyControl(readOnly, in: app, down: true)
            readOnly.tap()
            let plan = app.buttons["lio.exit.plan_now"]
            XCTAssertTrue(plan.exists)
            XCTAssertFalse(plan.isEnabled)
            XCTAssertFalse(app.buttons["lio.questions.continue"].isEnabled)
            XCTAssertFalse(app.buttons["lio.profile.pace"].isEnabled)
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "0")
            app.terminate()
        }
    }

    func testExplorationPlainAnswersEnglish() throws { try exerciseExplorationPlainAnswers(chinese: false) }
    func testExplorationPlainAnswersChinese() throws { try exerciseExplorationPlainAnswers(chinese: true) }

    private func exerciseExplorationPlainAnswers(chinese: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        do {
            for mode in ["--lio-exploration-legacy-acceptance", "--lio-exploration-profile-only-acceptance"] {
                launchExplorationReply(app, chinese: chinese, mode: mode)
                let answer = app.descendants(matching: .any).matching(identifier: "lio.answer").firstMatch
                XCTAssertTrue(answer.waitForExistence(timeout: 10))
                let visibleText = answer.descendants(matching: .staticText).allElementsBoundByIndex.map(\.label).joined(separator: "\n")
                XCTAssertTrue(visibleText.contains(chinese ? "之前的回答" : "Earlier reply"))
                XCTAssertFalse(visibleText.contains("**"))
                XCTAssertFalse(app.buttons["lio.questions.continue"].exists)
                XCTAssertFalse(app.buttons["lio.exit.plan_now"].exists)
                XCTAssertEqual(app.buttons["lio.profile.pace"].exists, mode == "--lio-exploration-profile-only-acceptance")
                try app.performAccessibilityAudit(for: .all)
                app.terminate()
            }
        }
    }

    func testExplorationProfileSendsOneEditedMessage() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for chinese in [false, true] {
            launchExplorationReply(app, chinese: chinese)
            let profile = app.buttons["lio.profile.pace"]
            XCTAssertTrue(profile.waitForExistence(timeout: 10))
            profile.tap()
            let sendControl = app.buttons["lio.profile.edit.send"]
            XCTAssertTrue(sendControl.waitForExistence(timeout: 5))
            XCTAssertGreaterThanOrEqual(sendControl.frame.height, 44)
            let field = app.textViews["lio.profile.edit.text"]
            XCTAssertTrue(field.waitForExistence(timeout: 5))
            XCTAssertTrue(field.isEnabled)
            field.tap()
            let old = field.value as! String
            field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + (chinese ? "节奏改为轻松" : "Pace: relaxed"))
            app.buttons["lio.profile.edit.send"].tap()
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "1")
            XCTAssertEqual(app.staticTexts["fixture.sent"].label, chinese ? "节奏改为轻松" : "Pace: relaxed")
            app.terminate()
        }
    }

    func testExplorationCanPlanWithoutSelections() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for chinese in [false, true] {
            launchExplorationReply(app, chinese: chinese)
            let submit = app.buttons["lio.questions.continue"]
            XCTAssertTrue(submit.waitForExistence(timeout: 10))
            XCTAssertFalse(submit.isEnabled)
            let plan = app.buttons["lio.exit.plan_now"]
            showExplorationReplyControl(plan, in: app, down: true)
            XCTAssertTrue(plan.isEnabled)
            plan.tap()
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "1")
            XCTAssertEqual(app.staticTexts["fixture.sent"].label, chinese ? "直接给我一个方案。" : "Please make a plan now.")
            app.terminate()
        }
    }

    func testExplorationProfileCancelDoesNotSend() throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for chinese in [false, true] {
            launchExplorationReply(app, chinese: chinese)
            let profile = app.buttons["lio.profile.pace"]
            XCTAssertTrue(profile.waitForExistence(timeout: 10))
            let before = profile.label
            profile.tap()
            let sendControl = app.buttons["lio.profile.edit.send"]
            XCTAssertTrue(sendControl.waitForExistence(timeout: 5))
            XCTAssertGreaterThanOrEqual(sendControl.frame.height, 44)
            let field = app.textViews["lio.profile.edit.text"]
            XCTAssertTrue(field.waitForExistence(timeout: 5))
            field.tap()
            field.typeText(" changed")
            app.buttons[chinese ? "取消" : "Cancel"].tap()
            XCTAssertEqual(app.staticTexts["fixture.count"].label, "0")
            XCTAssertEqual(profile.label, before)
            app.terminate()
        }
    }

    private func launchExplorationReply(_ app: XCUIApplication, chinese: Bool, dark: Bool = false, mode: String? = nil) {
        app.launchArguments = ["--lio-preview", "--lio-exploration-reply-acceptance",
                               "-cj.ui.language.v1", chinese ? "zh-Hans" : "en",
                               "-lio.ui.appearance.v1", dark ? "dark" : "light"]
        if let mode { app.launchArguments.append(mode) }
        app.launch()
    }

 func testRichItineraryEnglishLight() throws { try exerciseRichItinerary(false,false) }
 func testRichItineraryChineseLight() throws { try exerciseRichItinerary(true,false) }
 func testRichItineraryEnglishDark() throws { try exerciseRichItinerary(false,true) }
 func testRichItineraryChineseDark() throws { try exerciseRichItinerary(true,true) }
 private func exerciseRichItinerary(_ chinese:Bool,_ dark:Bool) throws {
  continueAfterFailure=false
  let app=XCUIApplication(bundleIdentifier:"space.go2china.lio.acceptance")
  app.launchArguments=["--lio-preview", "--lio-rich-itinerary-acceptance", "-cj.ui.language.v1", chinese ? "zh-Hans":"en"]+(dark ? ["--lio-rich-dark-acceptance"]:[])
  app.launchEnvironment=["G2C_ACCEPTANCE_MAP_LOADING":"synthetic-delegate-failure"]
  app.launch();defer{app.terminate()}
  func reveal(_ element:XCUIElement) {
   for _ in 0..<8 { if element.isHittable{return};app.swipeUp() }
   XCTAssertTrue(element.isHittable,app.debugDescription)
  }
  let first=app.buttons["lio.rich.stop.sight"]
  XCTAssertTrue(first.waitForExistence(timeout:10))
  try app.performAccessibilityAudit(for:.all)
  captureRichItinerary(app,"rich-day",chinese,dark)
  first.tap()
  let driver=app.buttons["lio.rich.driver"]
  XCTAssertTrue(driver.waitForExistence(timeout:5));XCTAssertTrue(driver.isEnabled)
  try app.performAccessibilityAudit(for:.all)
  driver.tap()
  let name=app.staticTexts["lio.rich.driver.name"]
  XCTAssertTrue(name.waitForExistence(timeout:5));XCTAssertEqual(name.label,"示例花园")
  XCTAssertEqual(app.staticTexts["lio.rich.driver.address"].label,"演示市示例路 1 号")
  try app.performAccessibilityAudit(for:.all)
  captureRichItinerary(app,"driver-card",chinese,dark)
  app.buttons["lio.rich.driver.done"].tap();app.buttons["lio.rich.detail.done"].tap()
  app.buttons["lio.rich.show-map"].tap()
  XCTAssertTrue(app.staticTexts[chinese ? "暂时无法显示地图":"Map unavailable"].waitForExistence(timeout:8))
  XCTAssertTrue(app.otherElements["lio.rich.map"].exists || app.images["lio.rich.map"].exists)
  let second=app.buttons["lio.rich.stop.meal"]
  reveal(second);second.tap()
  XCTAssertTrue(driver.waitForExistence(timeout:5));XCTAssertFalse(driver.isEnabled)
  try app.performAccessibilityAudit(for:.all)
  app.buttons["lio.rich.detail.done"].tap()
  let hotel=app.staticTexts[chinese ? "示例酒店甲":"Sample stay A"]
  reveal(hotel)
  try app.performAccessibilityAudit(for:.all)
  captureRichItinerary(app,"lodging",chinese,dark)
  for _ in 0..<8 { if app.buttons["lio.rich.day.2"].isHittable {break};app.swipeDown() }
  app.buttons["lio.rich.day.2"].tap()
  XCTAssertTrue(app.buttons["lio.rich.stop.transport"].exists)
  XCTAssertTrue(app.buttons["lio.rich.stop.free"].exists)
  try app.performAccessibilityAudit(for:.all)
  captureRichItinerary(app,"transport",chinese,dark)
  app.buttons["lio.rich.day.3"].tap()
  XCTAssertTrue(app.staticTexts[chinese ? "这一天还没有安排。":"No activities planned for this day yet."].exists)
  XCTAssertFalse(app.buttons["lio.rich.show-map"].exists)
  try app.performAccessibilityAudit(for:.all)
 }
 private func captureRichItinerary(_ app:XCUIApplication,_ label:String,_ chinese:Bool,_ dark:Bool) {
  let a=XCTAttachment(screenshot:app.screenshot());a.name=label+(chinese ? "-zh":"-en")+(dark ? "-dark":"-light");a.lifetime = .keepAlways;add(a)
 }

    func testExplorationReadEnglish() throws { try exerciseExplorationRead(false) }
    func testExplorationReadChinese() throws { try exerciseExplorationRead(true) }
    private func exerciseExplorationRead(_ chinese: Bool) throws {
        continueAfterFailure = false
        let app = XCUIApplication(bundleIdentifier: "space.go2china.lio.acceptance")
        for dark in [false, true] {
            app.launchArguments = ["--lio-preview", "--lio-exploration-read-acceptance", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
                + (dark ? ["--lio-read-dark-acceptance"] : [])
            app.launch()
            let prefix = "lio.questions.explore-" + (chinese ? "zh" : "en") + "."
            let first = app.buttons[prefix + "interests.history"]
            XCTAssertTrue(first.waitForExistence(timeout: 10), app.debugDescription)
            XCTAssertFalse(app.staticTexts["lio.exploration.fixture.unavailable"].exists)
            XCTAssertEqual(app.staticTexts["lio.exploration.send-count"].label, "0")
            try app.performAccessibilityAudit(for: .all)
            first.tap()
            app.buttons[prefix + "interests.nature"].tap()
            let submit = app.buttons["lio.questions.continue"]
            for _ in 0..<6 { if submit.isHittable { break }; app.swipeUp() }
            XCTAssertTrue(submit.isHittable, app.debugDescription)
            submit.tap()
            XCTAssertEqual(app.staticTexts["lio.exploration.send-count"].label, "1")
            XCTAssertEqual(app.staticTexts["lio.exploration.sent"].label, chinese ? "兴趣：历史\n兴趣：自然" : "Interests: History\nInterests: Nature")
            let rain = app.staticTexts[chinese ? "带一件雨衣。" : "Bring a raincoat."]
            for _ in 0..<6 { if rain.isHittable { break }; app.swipeUp() }
            XCTAssertTrue(rain.exists)
            try app.performAccessibilityAudit(for: .all)
            let attachment = XCTAttachment(screenshot: app.screenshot())
            attachment.name = "decoded-exploration-" + (chinese ? "zh" : "en") + (dark ? "-dark" : "-light")
            attachment.lifetime = .keepAlways; add(attachment)
            app.terminate()
        }
    }


 func testCalendarWireEnglish() throws { try exerciseCalendarWire(false) }
 func testCalendarWireChinese() throws { try exerciseCalendarWire(true) }
 private func exerciseCalendarWire(_ chinese:Bool) throws {
  continueAfterFailure = false
  let app = XCUIApplication(bundleIdentifier:"space.go2china.lio.acceptance")
  app.launchArguments = ["--lio-preview", "--lio-calendar-wire-acceptance", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
  app.launch(); defer { app.terminate() }
  let composer = app.descendants(matching:.any).matching(identifier:"lio.composer").firstMatch
  XCTAssertTrue(composer.waitForExistence(timeout:12),app.debugDescription)
  func ask(_ text:String) {
   composer.tap(); composer.typeText(text); app.buttons["lio.send"].tap()
  }
  func reveal(_ control:XCUIElement) {
   for _ in 0..<6 { if control.isHittable { return }; app.swipeUp() }
   XCTAssertTrue(control.isHittable,app.debugDescription)
  }
  func audit() throws {
   try app.performAccessibilityAudit(for: .all) { issue in
    let detail = XCTAttachment(string: issue.compactDescription + "\n" + issue.detailedDescription + "\n" + (issue.element?.debugDescription ?? "No element supplied") + "\n" + app.debugDescription)
    detail.name = "calendar-wire-audit"; detail.lifetime = .keepAlways; self.add(detail)
    return false
   }
  }
  let pending = app.staticTexts[chinese ? "出发日期待定":"Start date not set"]
  let chat = app.tabBars.buttons[chinese ? "聊天":"Chat"]
  ask("Plan three days, dates not set")
  XCTAssertTrue(pending.waitForExistence(timeout:12),app.debugDescription)
  captureCalendarWire(app,"calendar-http-card-before-audit",chinese)
  try audit()
  captureCalendarWire(app,"calendar-http-card",chinese)
  let show = app.buttons["lio.trip.show"].firstMatch; reveal(show); show.tap()
  XCTAssertTrue(pending.waitForExistence(timeout:10))
  let third = app.buttons["lio.trip.select-day.3"]
  XCTAssertTrue(third.waitForExistence(timeout:10),app.debugDescription)
  XCTAssertEqual(third.label,chinese ? "第 3 天":"Day 3")
  third.tap(); XCTAssertTrue(app.staticTexts["lio.trip.day.empty"].exists)
  try audit()
  captureCalendarWire(app,"calendar-http-trip",chinese)
  chat.tap()
  ask("Start on December 1")
  let undo = app.buttons["lio.chat.trip.undo"]
  XCTAssertTrue(undo.waitForExistence(timeout:12),app.debugDescription)
  let latest = app.buttons.matching(identifier:"lio.trip.show").allElementsBoundByIndex.last!
  reveal(latest); latest.tap()
  XCTAssertTrue(third.waitForExistence(timeout:10))
  XCTAssertEqual(third.label,"2026-12-03")
  try audit()
  captureCalendarWire(app,"calendar-http-dated",chinese)
  chat.tap(); reveal(undo); undo.tap()
  // The first read can reconcile before XCTest observes the transient spinner.
  XCTAssertTrue(pending.waitForExistence(timeout:16),app.debugDescription)
  reveal(latest); latest.tap()
  XCTAssertTrue(pending.waitForExistence(timeout:10),app.debugDescription)
  XCTAssertEqual(third.label,chinese ? "第 3 天":"Day 3")
  captureCalendarWire(app,"calendar-http-undone",chinese)
  showLioMe(app)
  let counts = app.staticTexts["fixture.counts"]
  XCTAssertTrue(counts.waitForExistence(timeout:5))
  XCTAssertEqual(counts.label,"sends=2 undoPosts=1 undoReads=1 details=3")
  let versions = app.staticTexts["fixture.history"]
  XCTAssertTrue(versions.waitForExistence(timeout:5))
  XCTAssertEqual(versions.label,"current=3 history=2,1")
 }
 private func captureCalendarWire(_ app:XCUIApplication,_ label:String,_ chinese:Bool) {
  let shot=XCTAttachment(screenshot:app.screenshot());shot.name=label+(chinese ? "-zh":"-en");shot.lifetime = .keepAlways;add(shot)
 }
}

@MainActor private final class LioClipboardSnapshot {
    private let items = UIPasteboard.general.items
    func restore() { UIPasteboard.general.items = items }
}

/// #1452: Memory moved from its own tab into Me, where it opens as a sheet with a Done button.
@MainActor private func openLioMemory(_ app: XCUIApplication, chinese: Bool) {
    let me = app.tabBars.buttons[chinese ? "我的" : "Me"]
    XCTAssertTrue(me.waitForExistence(timeout: 12))
    me.tap()
    let entry = app.buttons["lio.me.memory"]
    XCTAssertTrue(entry.waitForExistence(timeout: 8))
    entry.tap()
}

/// Close the Memory sheet before switching tabs, if it is open.
@MainActor private func closeLioMemory(_ app: XCUIApplication) {
    let done = app.buttons["lio.me.memory.done"]
    guard done.exists else { return }
    XCTAssertTrue(done.isHittable, done.debugDescription)
    done.tap()
}

/// #1452: fixture controls passed to Lio as the menu content now show in the Me tab, not in the chat menu.
/// Matched by label in both languages; the Tools tab is absent in some previews, so positions vary.
@MainActor private func showLioMe(_ app: XCUIApplication) { showLioTab(app, ["Me", "我的"]) }

@MainActor private func showLioTab(_ app: XCUIApplication, _ labels: [String]) {
    // The keyboard covers the tab bar: the chat menu button ends typing, then its sheet is closed again.
    if app.keyboards.firstMatch.exists, app.buttons["lio.menu"].exists {
        app.buttons["lio.menu"].tap()
        let done = app.navigationBars.buttons.matching(NSPredicate(format: "label IN %@", ["Done", "完成"])).firstMatch
        XCTAssertTrue(done.waitForExistence(timeout: 5), app.debugDescription)
        done.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
    }
    let tab = app.tabBars.buttons.matching(NSPredicate(format: "label IN %@", labels)).firstMatch
    XCTAssertTrue(tab.waitForExistence(timeout: 12), app.debugDescription)
    tab.tap()
}

@MainActor private func showLioChat(_ app: XCUIApplication) {
    let chat = app.tabBars.buttons.matching(NSPredicate(format: "label IN %@", ["Chat", "聊天"])).firstMatch
    XCTAssertTrue(chat.waitForExistence(timeout: 12), app.debugDescription)
    chat.tap()
}
