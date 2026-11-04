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

    static func requireLargestSystemFont() {
        print("M4_RUNNER_CONTENT_SIZE", UIApplication.shared.preferredContentSizeCategory.rawValue)
        XCTAssertEqual(UIApplication.shared.preferredContentSizeCategory,
                       .accessibilityExtraExtraExtraLarge,
                       "Set the approved device's actual system text size before this case")
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
