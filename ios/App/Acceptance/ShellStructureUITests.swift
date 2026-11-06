import XCTest
import Foundation

@MainActor final class ShellStructureUITests: XCTestCase {
    private let bundle = "space.go2china.shell.acceptance"
    private let fixtureURL = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private var runID = ""
    #if G2C_M4_DEVICE_ACCEPTANCE
    private lazy var deviceSession = M4DeviceTestSession(test: self, control: fixtureURL)
    #endif

    private func launch(mode: String? = nil, language: String = "en") {
        continueAfterFailure = false
        app?.terminate()
        app = XCUIApplication(bundleIdentifier: bundle)
        runID = UUID().uuidString
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable", "G2C_DEV_API_BASE_URL": "", "G2C_DEV_TOKEN": ""]
        if let mode {
            app.launchEnvironment.merge(["SHELL_FIXTURE_RUN": runID, "SHELL_FIXTURE_MEMORY": mode,
                "SHELL_FIXTURE_LANGUAGE": language, "SHELL_FIXTURE_URL": fixtureURL]) { _, new in new }
        } else { app.launchArguments = ["-cj.ui.language.v1", language] }
        #if G2C_M4_DEVICE_ACCEPTANCE
        app.launchEnvironment.merge(try! deviceSession.applicationEnvironment(endpoint: fixtureURL, injecting: false)) { _, value in value }
        #endif
        app.launch()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
    }

    private func tabs(_ labels: [String]) {
        let buttons = app.tabBars.buttons.allElementsBoundByIndex
        XCTAssertEqual(buttons.map(\.label), labels)
        XCTAssertEqual(buttons.count, 4)
        for pair in zip(buttons, buttons.dropFirst()) { XCTAssertLessThan(pair.0.frame.midX, pair.1.frame.midX) }
    }

    private func visibleControl(_ label: String) -> XCUIElement {
        let tab = ["Assistant","Trips","Plugins","Memory","助手","行程","插件","记忆"].contains(label)
        let routes = ["Account":"memory.account", "账号":"memory.account",
            "Delete account":"memory.accountDeletion", "注销账号":"memory.accountDeletion",
            "Language":"memory.language", "语言":"memory.language",
            "Help":"memory.help", "帮助":"memory.help",
            "Privacy notice (beta)":"memory.privacy", "隐私说明（内测版）":"memory.privacy",
            "Support":"memory.support", "支持":"memory.support"]
        let identifier = routes[label] ?? label
        let element: XCUIElement
        if tab { element = app.tabBars.buttons.matching(identifier:identifier).firstMatch }
        else if identifier == "support.email" {
            // SwiftUI Link has different AX element types across supported OSes.
            // Its exact product identifier is stable; no mail composition is sent.
            element = app.descendants(matching:.any).matching(identifier:identifier).firstMatch
        } else { element = app.buttons.matching(identifier:identifier).firstMatch }
        #if G2C_M4_DEVICE_ACCEPTANCE
        if !tab { deviceSession.revealControl(element, in: app, diagnosticIdentifier: identifier) }
        #else
        if !tab {
            for attempt in 0..<30 {
                let navigation = app.navigationBars.firstMatch
                let top = navigation.exists ? navigation.frame.maxY+4 : app.frame.minY+60
                let bar = app.tabBars.firstMatch
                let bottom = bar.exists ? bar.frame.minY : app.frame.maxY-24
                let frame = element.exists ? element.frame : .zero
                if element.exists && element.isHittable && frame.midY>top && frame.midY<bottom { break }
                let located = !frame.isEmpty && frame.midY.isFinite
                let down = located ? frame.midY<=top : attempt>=15
                let middle = (top+bottom)/2, step = min(150,(bottom-top)*0.35)
                let start = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? -step : step)))
                let end = app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width*0.85,dy:middle+(down ? step : -step)))
                start.press(forDuration:0.05,thenDragTo:end)
            }
        }
        #endif
        XCTAssertTrue(element.waitForExistence(timeout: 5), label)
        XCTAssertTrue(element.isHittable, label)
        return element
    }
    private func tap(_ label: String) {
        visibleControl(label).tap()
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
        #if G2C_M4_DEVICE_ACCEPTANCE
        // The keyboard accessory is outside the scrollable content bounds.
        // Use the same exact toolbar query as the signed feedback driver.
        let done = app.toolbars.buttons.matching(NSPredicate(format: "label IN %@", ["Done", "完成"]))
        XCTAssertTrue(done.element.waitForExistence(timeout: 8)); XCTAssertEqual(done.count, 1)
        XCTAssertTrue(done.element.isEnabled && done.element.isHittable); done.element.tap()
        let hidden = XCTNSPredicateExpectation(predicate: NSPredicate(format: "exists == false"), object: app.keyboards.firstMatch)
        XCTAssertEqual(XCTWaiter.wait(for: [hidden], timeout: 10), .completed)
        #else
        if app.buttons["Done"].exists { tap("Done") }
        else if app.buttons["完成"].exists { tap("完成") }
        #endif
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
        #if G2C_M4_DEVICE_ACCEPTANCE
        let (data, response) = try await deviceSession.data(from: url)
        #else
        let (data, response) = try await URLSession.shared.data(from: url)
        #endif
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
            let provider = app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Context Jump LLC")).firstMatch
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
            let mail = visibleControl("support.email")
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
            XCTAssertFalse(app.buttons["memory.account"].exists)
            XCTAssertFalse(app.buttons["memory.language"].exists)
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
            XCTAssertFalse(app.buttons["memory.account"].exists)
            XCTAssertFalse(app.buttons["memory.language"].exists)
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
                    // Returning preserves the list's scroll position. Revisit
                    // its state row before checking the unchanged value.
                    for _ in 0..<12 {
                        if app.staticTexts[expected].exists { break }
                        app.swipeDown()
                    }
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
            let card = app.staticTexts["plugins.didi.placeholder"]
            XCTAssertTrue(card.waitForExistence(timeout: 5))
            XCTAssertEqual(card.label, chinese ? "滴滴打车，即将推出，未来可在行程中直接叫车。目前尚未接入。" : "DiDi Ride-hailing, Coming soon, Request rides in China from your trip. Not connected yet.")
            XCTAssertFalse(app.buttons["plugins.didi.placeholder"].exists)
            text(chinese ? "更多插件将在后续版本提供。目前未接入任何工具。" : "More plugins are planned. No tools are connected.")
            XCTAssertEqual(app.buttons.count, 4) // Only the four Tab buttons; no pretend tool action.
            let observedRequests = try await requests()
            XCTAssertEqual(observedRequests, before)
            XCTAssertEqual(XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.count, 0)
            capture("plugins-inert-\(language)")
            app.terminate()
        }
    }
}
