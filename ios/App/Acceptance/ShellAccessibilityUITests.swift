import XCTest
import Foundation

@MainActor final class ShellAccessibilityUITests: XCTestCase {
    private let bundle = "space.go2china.shell.acceptance"
    private var app: XCUIApplication!

    private func capture(_ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot())
        image.name = name; image.lifetime = .keepAlways; add(image)
    }

    func testOrdinaryAppAccessibilityAudits() throws {
        continueAfterFailure = true // Collect all audit findings; any finding still fails the test.
        defer { app?.terminate() }
        for language in ["en", "zh-Hans"] {
            app?.terminate()
            app = XCUIApplication(bundleIdentifier: bundle)
            app.launchEnvironment = ["G2C_DEV_API_BASE_URL": "", "G2C_DEV_TOKEN": ""]
            app.launchArguments = ["-cj.ui.language.v1", language]
            app.launch()
            XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
            let labels = language == "en" ? ["Assistant", "Trips", "Plugins", "Memory"] : ["助手", "行程", "插件", "记忆"]
            for label in labels {
                app.tabBars.buttons[label].tap()
                try app.performAccessibilityAudit(for: .all) { issue in
                    let element = issue.element
                    let name = element?.exists == true ? element!.label : "<unavailable element>"
                    print("AX_AUDIT \(language) \(label): \(issue.compactDescription); \(name)")
                    return false // Report every issue; diagnostics never suppress an audit failure.
                }
                capture("accessibility-\(language)-\(label)")
            }
            app.buttons["memory.language"].tap()
            try app.performAccessibilityAudit(for: .all) { issue in
                print("AX_LANGUAGE \(language): \(issue.compactDescription)")
                return false
            }
            XCTAssertTrue(app.buttons[language == "en" ? "English" : "简体中文"].isSelected)
            capture("accessibility-language-picker-\(language)")
            app.navigationBars.buttons.element(boundBy: 0).tap()
            XCTAssertTrue(app.navigationBars[language == "en" ? "Memory" : "记忆"].exists)
        }
    }
    func testMaximumTextLayout() {
        continueAfterFailure = false
        app = XCUIApplication(bundleIdentifier: bundle)
        defer { app.terminate() }
        app.launchEnvironment = ["G2C_DEV_API_BASE_URL": "", "G2C_DEV_TOKEN": "",
            "SHELL_FIXTURE_RUN": UUID().uuidString, "SHELL_FIXTURE_MEMORY": "unconfigured",
            "SHELL_FIXTURE_LANGUAGE": "zh-Hans", "SHELL_FIXTURE_SIZE": "maximum"]
        app.launch()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        capture("maximum-text-assistant-top")
        app.scrollViews.firstMatch.swipeUp()
        capture("maximum-text-assistant-scrolled")
        app.tabBars.buttons["记忆"].tap()
        capture("maximum-text-memory-top")
        app.swipeUp()
        capture("maximum-text-memory-scrolled")
        for language in ["en", "zh-Hans"] {
            fixture(language: language, size: "maximum")
            app.tabBars.buttons[language == "en" ? "Plugins" : "插件"].tap()
            let card = app.staticTexts["plugins.didi.placeholder"]
            XCTAssertTrue(card.waitForExistence(timeout: 5))
            XCTAssertTrue(card.label.contains(language == "en" ? "Not connected yet." : "目前尚未接入。"))
            XCTAssertEqual(app.staticTexts.matching(identifier: "plugins.didi.placeholder").count, 1)
            XCTAssertFalse(app.buttons["plugins.didi.placeholder"].exists)
            XCTAssertEqual(app.buttons.count, 4)
            XCTAssertLessThanOrEqual(card.frame.maxX, app.frame.maxX)
            XCTAssertGreaterThanOrEqual(card.frame.minX, app.frame.minX)
            capture("plugins-maximum-text-" + language)
            app.swipeUp()
            visible(language == "en" ? "More plugins are planned." : "更多插件将在后续版本提供。")
            capture("plugins-maximum-text-scrolled-" + language)
        }
    }

    private let fixtureURL = "__FIXTURE_URL__"
    private var runID = ""

    private func fixture(language: String, memory: String = "unconfigured", trip: String = "unconfigured",
                         assistant: String = "notConnected", size: String = "standard", longText: Bool = false) {
        app?.terminate()
        app = XCUIApplication(bundleIdentifier: bundle)
        runID = UUID().uuidString
        app.launchEnvironment = ["G2C_DEV_API_BASE_URL": "", "G2C_DEV_TOKEN": "",
            "SHELL_FIXTURE_RUN": runID, "SHELL_FIXTURE_MEMORY": memory, "SHELL_FIXTURE_TRIPS": trip,
            "SHELL_FIXTURE_ASSISTANT": assistant, "SHELL_FIXTURE_LANGUAGE": language,
            "SHELL_FIXTURE_SIZE": size, "SHELL_FIXTURE_LONG_TEXT": longText ? "1" : "0",
            "SHELL_FIXTURE_URL": fixtureURL]
        app.launch()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
    }

    @discardableResult private func visible(_ label: String) -> XCUIElement {
        let element = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", label)).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: 5), label)
        return element
    }

    private func control(_ path: String) async throws -> [String] {
        let url = try XCTUnwrap(URL(string: fixtureURL + path + "?run=" + runID))
        let (data, response) = try await URLSession.shared.data(from: url)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return try JSONDecoder().decode([String].self, from: data)
    }

    func testAssistantStateSamplesInBothLanguages() {
        continueAfterFailure = false
        defer { app?.terminate() }
        let messages: [(String, String, String)] = [
            ("notConnected", "This service is not connected yet. No records have been loaded.", "此服务尚未接入。\n尚未读取记录。"),
            ("empty", "No records to show.", "暂无记录。"),
            ("loading", "Loading records…", "正在读取记录…"),
            ("failed", "Could not load records. Nothing is marked as saved.", "记录读取失败，未标记任何保存成功。"),
            ("offline", "You are offline. Current records cannot be verified.", "当前离线，无法核实最新记录。"),
            ("unknown", "The result is unknown. Do not repeat the action until the original result is checked.", "结果尚不明确，核对原操作结果前请勿重复操作。")
        ]
        for language in ["en", "zh-Hans"] {
            for (state, en, zh) in messages {
                fixture(language: language, assistant: state)
                let message = visible(language == "en" ? en : zh)
                XCTAssertTrue(message.isHittable)
                XCTAssertTrue(app.staticTexts["shell.fixture.observation"].exists)
                capture("assistant-\(state)-\(language)")
            }
        }
    }

    func testTripAndMemoryReadStatesInBothLanguages() async throws {
        continueAfterFailure = false
        defer { app?.terminate() }
        for language in ["en", "zh-Hans"] {
            let chinese = language != "en"
            for mode in ["unconfigured", "empty", "failed", "loading"] {
                fixture(language: language, memory: mode, trip: mode)
                app.tabBars.buttons[chinese ? "行程" : "Trips"].tap()
                let trip = mode == "unconfigured" ? (chinese ? "行程尚未连接，未读取任何记录。" : "Trips are not connected. No records have been loaded.")
                    : mode == "empty" ? (chinese ? "暂无行程" : "No trips returned")
                    : mode == "failed" ? (chinese ? "无法读取记录。" : "Could not read records.")
                    : (chinese ? "正在读取…" : "Loading…")
                visible(trip)
                capture("trips-\(mode)-\(language)")
                app.tabBars.buttons[chinese ? "记忆" : "Memory"].tap()
                let memory = mode == "unconfigured" ? (chinese ? "记忆尚未配置" : "Memory is not configured")
                    : mode == "empty" ? (chinese ? "暂无记忆分组" : "No memory groups")
                    : mode == "failed" ? (chinese ? "无法读取分组" : "Could not load groups")
                    : (chinese ? "正在读取记忆" : "Loading memories")
                visible(memory)
                capture("memory-\(mode)-\(language)")
                let observed = try await control("/audit")
                XCTAssertTrue(observed.allSatisfy { $0.hasPrefix("GET ") })
                XCTAssertEqual(observed.count, mode == "unconfigured" ? 0 : 2)
                if mode == "loading" {
                    _ = try await control("/release")
                    visible(chinese ? "暂无记忆分组" : "No memory groups")
                    app.tabBars.buttons[chinese ? "行程" : "Trips"].tap()
                    visible(chinese ? "暂无行程" : "No trips returned")
                }
                app.tabBars.buttons[chinese ? "插件" : "Plugins"].tap()
                visible(chinese ? "尚未开放" : "Coming soon")
                let after = try await control("/audit")
                XCTAssertEqual(after, observed)
            }
        }
    }

    func testLongTextKeyboardAndUnavailableControls() async throws {
        continueAfterFailure = false
        defer { app?.terminate() }
        for language in ["en", "zh-Hans"] {
            let chinese = language != "en"
            for size in ["standard", "large"] {
                fixture(language: language, size: size, longText: true)
                XCTAssertFalse(app.buttons[chinese ? "附件——尚未开放" : "Attachments — not available"].isEnabled)
                XCTAssertFalse(app.buttons[chinese ? "语音——尚未开放" : "Voice — not available"].isEnabled)
                XCTAssertFalse(app.buttons[chinese ? "礼物——尚未开放" : "Gifts — not available"].isEnabled)
                let field = app.descendants(matching: .any).matching(identifier: "assistant.draft").firstMatch
                XCTAssertTrue(field.waitForExistence(timeout: 5))
                let draft = chinese ? "Beijing 北京 158" : "Layout draft 158"
                field.tap(); field.typeText(draft)
                XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
                XCTAssertLessThanOrEqual(field.frame.maxY, app.keyboards.firstMatch.frame.minY)
                XCTAssertEqual(field.value as? String, draft)
                XCTAssertFalse(app.buttons[chinese ? "发送——服务尚未接入" : "Send — service not connected"].isEnabled)
                capture("keyboard-\(size)-\(language)")
                app.buttons[chinese ? "完成" : "Done"].tap()
                let end = app.buttons[chinese ? "反馈此回答的问题" : "Report a problem with this answer"]
                for _ in 0..<50 {
                    if end.isHittable && end.frame.maxY < field.frame.minY { break }
                    app.scrollViews.firstMatch.swipeUp()
                }
                XCTAssertTrue(end.isHittable)
                XCTAssertLessThan(end.frame.maxY, field.frame.minY)
                XCTAssertEqual(field.value as? String, draft)
                let observed = try await control("/audit")
                XCTAssertEqual(observed, [])
                capture("long-text-end-\(size)-\(language)")
            }
        }
    }

}
