import XCTest
import Foundation

@MainActor final class ShellStructureUITests: XCTestCase {
    private let bundle = "space.go2china.shell.acceptance"
    private let fixtureURL = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private var runID = ""

    private func launch(mode: String? = nil, language: String = "en") {
        continueAfterFailure = false
        app?.terminate()
        app = XCUIApplication(bundleIdentifier: bundle)
        runID = UUID().uuidString
        app.launchEnvironment = ["G2C_DEV_API_BASE_URL": "", "G2C_DEV_TOKEN": ""]
        if let mode {
            app.launchEnvironment.merge(["SHELL_FIXTURE_RUN": runID, "SHELL_FIXTURE_MEMORY": mode,
                "SHELL_FIXTURE_LANGUAGE": language, "SHELL_FIXTURE_URL": fixtureURL]) { _, new in new }
        } else { app.launchArguments = ["-cj.ui.language.v1", language] }
        app.launch()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
    }

    private func tabs(_ labels: [String]) {
        let buttons = app.tabBars.buttons.allElementsBoundByIndex
        XCTAssertEqual(buttons.map(\.label), labels)
        XCTAssertEqual(buttons.count, 4)
        for pair in zip(buttons, buttons.dropFirst()) { XCTAssertLessThan(pair.0.frame.midX, pair.1.frame.midX) }
    }

    private func tap(_ label: String) {
        let element = app.buttons.matching(identifier: label).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: 5), label)
        if !element.isHittable { app.swipeUp() }
        XCTAssertTrue(element.isHittable, label)
        element.tap()
    }

    private func text(_ label: String) {
        XCTAssertTrue(app.staticTexts[label].waitForExistence(timeout: 5), label)
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }

    private func enterDraft() {
        let field = app.descendants(matching: .any).matching(identifier: "assistant.draft").firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap(); field.typeText("Beijing draft 157")
        if app.buttons["Done"].exists { tap("Done") }
        else if app.buttons["完成"].exists { tap("完成") }
    }

    private func draftRetained() {
        let field = app.descendants(matching: .any).matching(identifier: "assistant.draft").firstMatch
        XCTAssertEqual(field.value as? String, "Beijing draft 157")
    }

    private func observation() throws -> [String: String] {
        let value = try XCTUnwrap(app.staticTexts["shell.fixture.observation"].value as? String)
        return try JSONDecoder().decode([String: String].self, from: Data(value.utf8))
    }

    private func requests() async throws -> [String] {
        let url = try XCTUnwrap(URL(string: fixtureURL + "/audit?run=" + runID))
        let (data, response) = try await URLSession.shared.data(from: url)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        return try JSONDecoder().decode([String].self, from: data)
    }

    func testOrdinaryHelpPrivacySupportInBothLanguages() {
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            launch(language: language)
            tap(chinese ? "记忆" : "Memory")
            tap(chinese ? "帮助" : "Help")
            XCTAssertTrue(app.navigationBars[chinese ? "帮助" : "Help"].exists)
            text(chinese ? "首次使用与建号" : "Getting started")
            capture("help-" + language)
            app.navigationBars.buttons.element(boundBy: 0).tap()
            tap(chinese ? "隐私说明（内测版）" : "Privacy notice (beta)")
            XCTAssertTrue(app.navigationBars[chinese ? "隐私说明（内测版）" : "Privacy notice (beta)"].exists)
            let provider = app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "Context Jump LLC")).firstMatch
            XCTAssertTrue(provider.waitForExistence(timeout: 5))
            capture("privacy-provider-" + language)
            let support = app.buttons[chinese ? "支持" : "Support"]
            for _ in 0..<12 {
                if support.exists && support.isHittable { break }
                app.swipeUp()
            }
            XCTAssertTrue(support.isHittable); support.tap()
            XCTAssertTrue(app.navigationBars[chinese ? "支持" : "Support"].exists)
            text("hello@go2china.space")
            let mail = app.buttons["support.email"]
            XCTAssertTrue(mail.exists && mail.isHittable)
            XCTAssertTrue(mail.label.contains("hello@go2china.space"))
            XCTAssertFalse(app.staticTexts["support@go2china.space"].exists)
            XCTAssertFalse(app.staticTexts["jtcao@go2china.space"].exists)
            capture("support-" + language)
            app.terminate()
        }
    }

    func testOrdinaryAppTabsLanguageAndDraft() {
        launch()
        tabs(["Assistant", "Trips", "Plugins", "Memory"])
        enterDraft()
        for tab in ["Assistant", "Trips", "Plugins"] {
            tap(tab)
            XCTAssertFalse(app.buttons["Account"].exists)
            XCTAssertFalse(app.buttons["Language"].exists)
        }
        tap("Memory"); tap("Language")
        text("Saved on this device. Switching language keeps your current navigation and unsent draft.")
        tap("简体中文")
        tabs(["助手", "行程", "插件", "记忆"])
        XCTAssertTrue(app.navigationBars["语言"].exists)
        text("保存在此设备。\n切换语言会保留当前导航和未发送草稿。")
        tap("助手"); draftRetained()
        for tab in ["助手", "行程", "插件"] {
            tap(tab)
            XCTAssertFalse(app.buttons["账号"].exists)
            XCTAssertFalse(app.buttons["语言"].exists)
        }
        tap("记忆")
        XCTAssertTrue(app.navigationBars["语言"].exists)
        capture("ordinary-chinese-language-navigation")
        tap("English"); tabs(["Assistant", "Trips", "Plugins", "Memory"])
        tap("Assistant"); draftRetained()
        tap("Memory"); tap("简体中文")
        app.terminate(); app.launchArguments = []; app.launch()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        tabs(["助手", "行程", "插件", "记忆"])
        capture("ordinary-language-persisted")
    }

    func testMemoryStatesKeepSettingsReachable() {
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            for mode in ["unconfigured", "empty", "failed"] {
                launch(mode: mode, language: language)
                tap(chinese ? "记忆" : "Memory")
                let expected = mode == "empty" ? (chinese ? "暂无记忆分组" : "No memory groups")
                    : mode == "failed" ? (chinese ? "无法读取分组" : "Could not load groups")
                    : (chinese ? "记忆尚未配置" : "Memory is not configured")
                text(expected)
                for label in (chinese ? ["账号", "语言", "帮助", "隐私说明（内测版）"] : ["Account", "Language", "Help", "Privacy notice (beta)"]) {
                    tap(label)
                    let title = label == "Privacy notice (beta)" ? "Privacy notice (beta)"
                        : label == "隐私说明（内测版）" ? "隐私说明（内测版）" : label
                    XCTAssertTrue(app.navigationBars[title].exists, title)
                    if label == "Account" || label == "账号" {
                        text(chinese ? "尚无已验证的账号会话。" : "No verified account session.")
                    }
                    let back = app.navigationBars.buttons.element(boundBy: 0)
                    XCTAssertTrue(back.isHittable); back.tap()
                    text(expected)
                }
                capture("memory-\(mode)-\(language)")
                app.terminate()
            }
        }
    }

    func testLanguagePreservesReferencesAndDoesNotRepeatRequests() async throws {
        launch(mode: "empty")
        enterDraft()
        tap("Memory"); text("No memory groups"); tap("Language")
        let before = try observation()
        let originalRequests = try await requests()
        XCTAssertEqual(originalRequests, ["GET /v1/memory-groups"])
        for language in ["简体中文", "English", "简体中文"] {
            tap(language)
            let after = try observation()
            for key in ["conversation", "trip", "draft", "draftRevision", "generation", "memoryPath", "tripPath", "tab"] {
                XCTAssertEqual(after[key], before[key], key)
            }
            let observedRequests = try await requests()
            XCTAssertEqual(observedRequests, originalRequests)
        }
        capture("language-keeps-fixture-identities-and-draft")
    }

    func testPluginsAreInertInBothLanguages() async throws {
        for language in ["en", "zh-Hans"] {
            let chinese = language == "zh-Hans"
            launch(mode: "empty", language: language)
            tap(chinese ? "记忆" : "Memory"); text(chinese ? "暂无记忆分组" : "No memory groups")
            let before = try await requests()
            tap(chinese ? "插件" : "Plugins")
            text(chinese ? "尚未开放" : "Coming soon")
            XCTAssertEqual(app.buttons.count, 4) // Only the four Tab buttons; no pretend tool action.
            let observedRequests = try await requests()
            XCTAssertEqual(observedRequests, before)
            XCTAssertEqual(XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count, 0)
            capture("plugins-inert-\(language)")
            app.terminate()
        }
    }
}
