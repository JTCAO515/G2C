import XCTest
import Foundation

@MainActor final class AccountCleanupComponentUITests: XCTestCase {
    let control = "__CONTROL_URL__"
    var app: XCUIApplication!
    struct Operation: Decodable { let operation_id: String; let action_id: String; let input_digest: String; let phase: String }
    struct Account: Decodable { let operations: [Operation]; let fences: Int; let feedback: Int; let cleanup_role: String; let runtime_role: String }
    struct Proof: Decodable { let accounts: [String: Account]; let provider_calls: Int }
    @discardableResult func call(_ path: String, _ name: String, values: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        url.queryItems = values.merging(["case":name]) { _, next in next }.map { .init(name: $0.key, value: $0.value) }
        let (bytes, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, path)
        return bytes
    }
    func proof(_ name: String) async throws -> Proof { try JSONDecoder().decode(Proof.self, from: await call("/proof", name)) }
    func launch(_ name: String) {
        continueAfterFailure = false
        app?.terminate(); app = XCUIApplication(bundleIdentifier: "space.go2china.cleanup.component")
        app.launchEnvironment = ["OS_ACTIVITY_MODE":"disable", "G2C_COMPONENT_CONTROL":control+"?case="+name]
        app.launch(); status("ready")
    }
    func tap(_ id: String) {
        let query = app.buttons.matching(identifier: id), button = query.element
        for attempt in 0..<35 {
            let frame = button.exists ? button.frame : .zero
            let top = app.navigationBars.element.frame.maxY + 8, bottom = app.frame.maxY - 40
            if button.exists && button.isHittable && frame.minY >= top && frame.maxY <= bottom { break }
            let down = frame.isEmpty ? (attempt / 8) % 2 == 1 : frame.midY < top
            let middle = (top + bottom) / 2, step = min(100, (bottom - top) * 0.15)
            let start = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: app.frame.width * 0.85, dy: middle + (down ? -step : step)))
            let end = app.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: app.frame.width * 0.85, dy: middle + (down ? step : -step)))
            start.press(forDuration: 0.05, thenDragTo: end)
        }
        XCTAssertEqual(query.count, 1, id); XCTAssertTrue(button.isHittable && button.isEnabled, id)
        button.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
    }
    func text(_ id: String, equals expected: String) {
        let element = app.staticTexts[id]
        let wait = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", expected), object: element)
        XCTAssertEqual(XCTWaiter.wait(for: [wait], timeout: 25), .completed, id)
    }
    func status(_ expected: String) { text("cleanup.component.status", equals: expected) }
    func contains(_ id: String, _ fragment: String) {
        let wait = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", fragment), object: app.staticTexts[id])
        XCTAssertEqual(XCTWaiter.wait(for: [wait], timeout: 25), .completed, id)
    }
    func capture(_ name: String) { let a = XCTAttachment(screenshot: app.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a) }
    func initial(_ name: String) async throws -> String {
        launch(name); tap("cleanup.component.signin.A"); status("verified-A")
        tap("cleanup.component.prepare"); status("awaiting-confirmation")
        let evidence = try await proof(name)
        XCTAssertEqual(evidence.provider_calls, 2)
        XCTAssertEqual(evidence.accounts["A"]?.operations.count, 1)
        let original = try XCTUnwrap(evidence.accounts["A"]?.operations.first?.operation_id)
        text("cleanup.component.operation", equals: original)
        XCTAssertEqual(evidence.accounts["A"]?.cleanup_role, "cj_local_cleanup")
        XCTAssertEqual(evidence.accounts["A"]?.runtime_role, "cj_m1_runtime")
        return original
    }
    func testActualCommittedUnknownReopen() async throws {
        let name = "testActualCommittedUnknownReopen", original = try await initial(name); defer { app?.terminate() }
        try await call("/fault", name, values: ["kind":"confirmation"])
        tap("cleanup.component.confirm"); status("confirmation-unknown"); text("cleanup.component.sdk", equals: "blocked")
        let committed = try await proof(name)
        XCTAssertEqual(committed.accounts["A"]?.operations.first?.operation_id, original)
        XCTAssertEqual(committed.accounts["A"]?.fences, 1); XCTAssertEqual(committed.accounts["A"]?.feedback, 0)
        launch(name); tap("cleanup.component.restore"); status("restored-original")
        text("cleanup.component.operation", equals: original); text("cleanup.component.sdk", equals: "blocked")
        tap("cleanup.component.read"); status("in_progress")
        contains("cleanup.component.result", "business=revoked;online=complete;all-devices=false")
        capture("actual-original-restricted-progress")
        tap("cleanup.component.signin.A"); status("verification-denied")
        tap("cleanup.component.signin.B"); status("verified-B")
        text("cleanup.component.operation", equals: "No operation / 无操作")
        try await call("/validate", name)
    }
    func testActualPreparationUnknown() async throws {
        let name = "testActualPreparationUnknown"; defer { app?.terminate() }
        launch(name); tap("cleanup.component.signin.A"); status("verified-A")
        try await call("/fault", name, values: ["kind":"preparation"])
        tap("cleanup.component.prepare"); status("preparation-unknown")
        let before = try await proof(name), original = try XCTUnwrap(before.accounts["A"]?.operations.first?.operation_id)
        launch(name); tap("cleanup.component.signin.A"); status("verified-A")
        tap("cleanup.component.read"); status("awaiting-confirmation")
        text("cleanup.component.operation", equals: original)
        capture("actual-original-preparation-recovered")
        try await call("/validate", name)
    }
    func testActualFullInventoryBlocked() async throws {
        let name = "testActualFullInventoryBlocked", original = try await initial(name); defer { app?.terminate() }
        tap("cleanup.component.confirm"); status("blocked")
        text("cleanup.component.operation", equals: original)
        contains("cleanup.component.result", "business=unchanged")
        text("cleanup.component.sdk", equals: "stored")
        let blocked = try await proof(name)
        XCTAssertEqual(blocked.accounts["A"]?.fences, 0); XCTAssertEqual(blocked.accounts["A"]?.feedback, 1)
        tap("cleanup.component.read"); status("awaiting_confirmation")
        contains("cleanup.component.result", "business=unchanged")
        capture("actual-full-inventory-blocked")
        try await call("/validate", name)
    }
}
