#if DEBUG && G2C_M4_DEVICE_ACCEPTANCE
import Foundation
import UIKit
import XCTest

/// Generated XCTest-only support. The operator input stays in the App's Caches;
/// JWTs never become XCTest launch environment or activity metadata.
@MainActor final class M4DeviceTestSession {
    private unowned let test: XCTestCase
    private let control: URL
    private var prepared = false

    init(test: XCTestCase, control: String) {
        self.test = test
        self.control = URL(string: control)!
    }

    /// SwiftUI's vertical TextField may expose either editable UIKit role.
    /// Keep the exact identifier and let the caller assert a single input.
    func textInputQuery(_ identifier: String, in app: XCUIApplication) -> XCUIElementQuery {
        let roles = [XCUIElement.ElementType.textField.rawValue, XCUIElement.ElementType.textView.rawValue]
        return app.descendants(matching: .any).matching(identifier: identifier)
            .matching(NSPredicate(format: "elementType IN %@", roles))
    }

    /// Caller focuses the exact field and places its caret at the visible end.
    /// Each keyboard event must remove exactly one old character before typing.
    static func clearFocusedTextWithKeyboard(_ field: XCUIElement) {
        var retained = field.value as? String ?? ""
        while !retained.isEmpty {
            field.typeText(XCUIKeyboardKey.delete.rawValue); retained.removeLast()
            XCTAssertEqual(Array((field.value as? String ?? "").utf8),Array(retained.utf8),"Each delete must remove exactly the last old character")
        }
        XCTAssertEqual(Array((field.value as? String ?? "").utf8),[],"The old value must be empty before replacement")
    }

    /// Use actual visible content bounds; keyboard accessories are outside Keyboard.frame.
    /// This follows the existing Needs driver gutter drag, away from editable rows.
    func revealControl(_ element: XCUIElement, in app: XCUIApplication, keyboardDone: XCUIElement? = nil, diagnosticIdentifier: String? = nil) {
        for attempt in 0..<20 {
            let keyboard=app.keyboards.firstMatch
            if keyboardDone != nil && !keyboard.exists {
                element.tap();XCTAssertTrue(keyboard.waitForExistence(timeout:5))
            }
            let bar=app.navigationBars.firstMatch,tabs=app.tabBars.firstMatch
            let top=bar.exists ? bar.frame.maxY : app.frame.minY+60
            var bottom=tabs.exists ? tabs.frame.minY : app.frame.maxY-20
            if keyboard.exists {bottom=min(bottom,keyboard.frame.minY)}
            if let keyboardDone,keyboardDone.exists {bottom=min(bottom,keyboardDone.frame.minY)}
            let frame=element.exists ? element.frame : .zero
            if let diagnosticIdentifier,attempt==0 || attempt==19 {
                print("M4_EXACT_REVEAL",diagnosticIdentifier,"exists",element.exists,"frame",frame,"hittable",element.exists && element.isHittable,
                    "bar",bar.exists ? bar.label:"none",bar.exists ? bar.frame:.zero,"bar_hittable",bar.exists && bar.isHittable,
                    "tabs",tabs.exists ? tabs.frame:.zero,"limits",top,bottom)
            }
            let located = !frame.isEmpty && frame.minY.isFinite && frame.maxY.isFinite
            // A fully visible cell may meet the navigation boundary exactly.
            // Allow only half a physical pixel for AX floating-point rounding,
            // rather than requiring an extra four-point gutter that cannot scroll.
            let tolerance=0.5/UIScreen.main.scale
            let fits=located && frame.height<=bottom-top+tolerance
            let within=located && (fits ? frame.minY>=top-tolerance && frame.maxY<=bottom+tolerance : frame.midY>top && frame.midY<bottom)
            if within && element.isHittable {return}
            let down=located ? frame.minY<top-tolerance : attempt>=10
            let middle=(top+bottom)/2,step=min(125,(bottom-top)*0.3)
            let start=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width-6,dy:middle+(down ? -step:step)))
            let end=app.coordinate(withNormalizedOffset:.zero).withOffset(CGVector(dx:app.frame.width-6,dy:middle+(down ? step:-step)))
            start.press(forDuration:0.05,thenDragTo:end)
        }
        let shot=XCTAttachment(screenshot:app.screenshot());shot.name="unexposed-control";shot.lifetime = .keepAlways;test.add(shot)
        XCTFail("Exact control must be exposed above the keyboard/accessory and within page content")
    }

    /// Verification can rebuild the root and select Trips. Reopen the account
    /// surface to read the same result; never repeat sign-in or another request.
    func requireAccount(_ subject: String, in app: XCUIApplication) {
        let status=app.staticTexts.matching(identifier:"account.development.status").firstMatch
        let deadline=Date().addingTimeInterval(20)
        while Date()<deadline {
            if status.exists && status.label.contains(subject) {return}
            if !status.exists {
                let memory=app.tabBars.buttons.matching(NSPredicate(format:"label IN %@",["Memory","记忆"]))
                XCTAssertEqual(memory.count,1);XCTAssertTrue(memory.element.isHittable);memory.element.tap()
                if !status.waitForExistence(timeout:1) {
                    let entry=app.buttons.matching(identifier:"memory.account").firstMatch
                    revealControl(entry,in:app);XCTAssertTrue(entry.isEnabled);entry.tap()
                }
            }
            let matched=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",subject),object:status)
            if XCTWaiter.wait(for:[matched],timeout:1) == .completed {return}
        }
        let shot=XCTAttachment(screenshot:app.screenshot());shot.name="account-result-not-readable";shot.lifetime = .keepAlways;test.add(shot)
        XCTAssertTrue(status.exists,"Original account result must be readable")
        XCTAssertTrue(status.label.contains(subject),status.exists ? status.label:"account result missing")
    }

    private func handle(_ alert: XCUIElement) -> Bool {
        let message = alert.staticTexts.allElementsBoundByIndex.map(\.label)
            .joined(separator: " ").lowercased()
        guard message.contains("g2c") else { return false }
        let labels: [String]
        if message.contains("无线数据") || message.contains("wireless data") {
            labels = ["仅限无线局域网", "WLAN Only", "Wi-Fi Only"]
        } else if message.contains("本地网络") || message.contains("local network") {
            labels = ["允许", "Allow"]
        } else { return false }
        let button = alert.buttons.matching(NSPredicate(format: "label IN %@", labels)).firstMatch
        guard button.exists && button.isHittable else { return false }
        button.tap()
        return true
    }

    func handleAppConsent() {
        let alert = XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.firstMatch
        if alert.exists { _ = handle(alert) }
    }

    func waitForAppNetworkConsent() {
        // A fresh App asks only after its first sign-in/restore request, not
        // necessarily at launch. Match the tested #398 permission path.
        for _ in 0..<16 {
            handleAppConsent()
            Thread.sleep(forTimeInterval: 0.25)
        }
    }

    func data(_ path: String) async throws -> (Data, URLResponse) {
        try await data(from: XCTUnwrap(URL(string: control.absoluteString + path)))
    }

    func data(from url: URL) async throws -> (Data, URLResponse) {
        if !prepared {
            test.addUIInterruptionMonitor(withDescription: "G2C local network and Wi-Fi only") {
                [weak self] alert in self?.handle(alert) ?? false
            }
            print("M4_CONTROL_APPLICATION_STATE", UIApplication.shared.applicationState.rawValue)
            if UIApplication.shared.applicationState != .active {
                let runner = XCUIApplication(bundleIdentifier: try XCTUnwrap(Bundle.main.bundleIdentifier))
                runner.activate()
            }
            try M4DeviceControl.triggerLocalNetworkAlert()
            let alert = XCUIApplication(bundleIdentifier: "com.apple.springboard").alerts.firstMatch
            if alert.waitForExistence(timeout: 3) { _ = handle(alert) }
            prepared = true
        }
        let permissions = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                self?.handleAppConsent()
                do { try await Task.sleep(for: .milliseconds(500)) }
                catch { return }
            }
        }
        defer { permissions.cancel() }
        let (denied, response) = try await M4DeviceControl.unauthenticatedData(from: url)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 403)
        XCTAssertFalse(String(decoding: denied, as: UTF8.self).contains("accounts"))
        return try await M4DeviceControl.data(from: url)
    }

    func stageAccounts(caseID: String? = nil) async throws {
        var components = URLComponents(url: control.appendingPathComponent("m4-stage-accounts"),
                                       resolvingAgainstBaseURL: false)!
        if let caseID { components.queryItems = [.init(name: "case", value: caseID)] }
        let (_, response) = try await data(from: XCTUnwrap(components.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
    }

    func applicationEnvironment(endpoint: String, injecting: Bool,
                                additionalEndpoints: [String] = []) throws -> [String: String] {
        let url = try XCTUnwrap(URL(string: endpoint))
        // Host approval comes from the operator-generated control endpoint,
        // not from an arbitrary API URL supplied by a fixture response.
        guard url.scheme == "https", url.host == control.host,
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
              url.path.isEmpty || url.path == "/", let primary = url.port, (1...65535).contains(primary) else {
            throw M4LocalTLSFailure.invalidCertificate
        }
        var extras = Set<Int>()
        for endpoint in additionalEndpoints {
            guard let value = URL(string: endpoint), value.scheme == "https", value.host == control.host,
                  value.user == nil, value.password == nil, value.query == nil, value.fragment == nil,
                  value.path.isEmpty || value.path == "/", let port = value.port, (1...65535).contains(port) else {
                throw M4LocalTLSFailure.invalidConfiguration
            }
            if port != primary { extras.insert(port) }
        }
        var result = ["G2C_M4_LOCAL_HOST": try XCTUnwrap(control.host),
                      "G2C_M4_LOCAL_PORT": String(primary),
                      "G2C_M4_LOCAL_EXTRA_PORTS": String(decoding: try JSONEncoder().encode(extras.sorted()), as: UTF8.self)]
        if injecting { result["G2C_M4_ACCOUNTS_FILE"] = "G2CM4DeviceAccounts.json" }
        return result
    }
}
#endif
