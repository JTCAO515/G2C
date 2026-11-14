import XCTest
import Foundation

@MainActor final class AccountDeletionUITests: XCTestCase {
    private let bundle = "space.go2china.shell.acceptance"
    private let fixtureURL = "__FIXTURE_URL__"
    private var app: XCUIApplication!
    private var runID = ""
    #if G2C_M4_DEVICE_ACCEPTANCE
    private lazy var deviceSession = M4DeviceTestSession(test: self, control: fixtureURL)
    #endif

    private func launch(language: String, mode: String? = nil) {
        continueAfterFailure = true // Collect all findings; any finding still fails.
        app?.terminate()
        app = XCUIApplication(bundleIdentifier: bundle)
        app.launchArguments = ["-cj.ui.language.v1", language]
        app.launchEnvironment = ["G2C_DEV_API_BASE_URL": "", "G2C_DEV_TOKEN": "", "OS_ACTIVITY_MODE": "disable"]
        runID = UUID().uuidString
        if let mode {
            app.launchEnvironment.merge(["SHELL_FIXTURE_RUN": runID, "SHELL_FIXTURE_MEMORY": mode,
                "SHELL_FIXTURE_LANGUAGE": language, "SHELL_FIXTURE_URL": fixtureURL]) { _, new in new }
        }
        #if G2C_M4_DEVICE_ACCEPTANCE
        app.launchEnvironment.merge(try! deviceSession.applicationEnvironment(endpoint: fixtureURL, injecting: false)) { _, value in value }
        #endif
        app.launch()
        #if G2C_M4_DEVICE_ACCEPTANCE
        deviceSession.waitForAppNetworkConsent()
        #endif
        XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 10))
        app.tabBars.buttons[language == "en" ? "Memory" : "记忆"].tap()
    }

    private func reveal(_ element: XCUIElement) {
        for _ in 0..<15 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTFail("Element not reachable: " + element.identifier)
    }

    private func tap(_ id: String) {
        let matches = app.buttons.matching(identifier: id)
        let element = matches.element
        reveal(element)
        XCTAssertEqual(matches.count, 1, id)
        element.tap()
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }

    private func explanation(language: String, audit: Bool = false) throws {
        XCTAssertTrue(app.navigationBars[language == "en" ? "Delete account" : "注销账号"].waitForExistence(timeout: 5))
        let expected = language == "en" ? "Account deletion is not available yet. No deletion request has been sent." : "账号注销尚未开放，未发送注销请求。"
        XCTAssertEqual(app.staticTexts["account.deletion.unavailable"].label, expected)
        for (id, fragment) in [
            ("memoryScope", language == "en" ? "keeps your account and original chat" : "保留账号和原聊天"),
            ("accountScope", language == "en" ? "chats, trips, candidates" : "聊天、行程、候选"),
            ("progressScope", language == "en" ? "separate results" : "两项独立结果"),
            ("offlineScope", "14"), ("retentionScope", "30")
        ] {
            let paragraph = app.staticTexts["account.deletion." + id]
            reveal(paragraph)
            XCTAssertTrue(paragraph.label.contains(fragment))
            XCTAssertGreaterThanOrEqual(paragraph.frame.minX, app.frame.minX)
            XCTAssertLessThanOrEqual(paragraph.frame.maxX, app.frame.maxX)
            if audit { try app.performAccessibilityAudit(for: .all) { issue in
                print("AX_DELETION: \(issue.compactDescription); element=\(issue.element?.label ?? "<unavailable>"); id=\(issue.element?.identifier ?? "<none>")")
                return false
            } } // No issue is ignored.
            capture("deletion-\(language)-\(id)")
        }
        XCTAssertFalse(app.buttons["account.deletion.submit"].exists)
    }

    func testOrdinaryEntryAndAccountInBothLanguages() throws {
        defer { app?.terminate() }
        for language in ["en", "zh-Hans"] {
            launch(language: language)
            try app.performAccessibilityAudit(for: .all) { issue in
                print("AX_DELETION_ROOT: \(issue.compactDescription); element=\(issue.element?.label ?? "<unavailable>")")
                return false
            }
            tap("memory.accountDeletion")
            try explanation(language: language)
            app.navigationBars.buttons.element(boundBy: 0).tap()
            app.swipeDown()
            tap("memory.account")
            tap("account.deletion.open")
            try explanation(language: language)
        }
    }

    private func auditRequests() async throws {
        let url = try XCTUnwrap(URL(string: fixtureURL + "/audit?run=" + runID))
        #if G2C_M4_DEVICE_ACCEPTANCE
        let (data, response) = try await deviceSession.data(from: url, restoring: app)
        #else
        let (data, response) = try await URLSession.shared.data(from: url)
        #endif
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        let paths = try JSONDecoder().decode([String].self, from: data)
        XCTAssertEqual(paths, ["GET /v1/memory-groups"])
    }

    func testEmptyAndFailedMemoryEntry() async throws {
        defer { app?.terminate() }
        for language in ["en", "zh-Hans"] {
            for mode in ["empty", "failed"] {
                launch(language: language, mode: mode)
                let status = language == "en" ? (mode == "empty" ? "No memory groups" : "Could not load groups")
                    : (mode == "empty" ? "暂无记忆分组" : "无法读取分组")
                XCTAssertTrue(app.staticTexts[status].waitForExistence(timeout: 5))
                tap("memory.accountDeletion")
                try explanation(language: language)
                try await auditRequests()
            }
        }
    }

    func testMaximumTextAndFullAccessibilityAudit() throws {
        defer { app?.terminate() }
        for language in ["en", "zh-Hans"] {
            launch(language: language, mode: "unconfigured")
            let observation = app.staticTexts["shell.fixture.observation"]
            let data = try XCTUnwrap((observation.value as? String)?.data(using: .utf8))
            let values = try JSONDecoder().decode([String: String].self, from: data)
            print("DELETION_FONT_OBSERVATION", values["contentSizeCategory"] as Any)
            tap("memory.accountDeletion")
            try app.performAccessibilityAudit(for: .all) { issue in
                print("AX_DELETION: \(issue.compactDescription); element=\(issue.element?.label ?? "<unavailable>"); id=\(issue.element?.identifier ?? "<none>")")
                return false
            }
            try explanation(language: language, audit: true)
        }
    }
}
