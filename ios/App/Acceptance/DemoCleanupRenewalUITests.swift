import XCTest

@MainActor final class DemoCleanupRenewalUITests: XCTestCase {
    func testActualBetaCoordinatorKeepsOriginalCleanupAcrossRenewal() {
        let app = XCUIApplication(bundleIdentifier: "space.go2china.b691.acceptance")
        app.launchEnvironment["B691_REFUSAL_MODE"] = "__B691_REFUSAL_MODE__"
        app.launchEnvironment["B691_ROOT_LIFECYCLE"] = "__B691_ROOT_MODE__"
        app.launchEnvironment["B691_LOCAL_ENDPOINT"] = "__B691_LOCAL_ENDPOINT__"
        app.launch()
        let status = app.staticTexts["b691.status"]
        XCTAssertTrue(status.waitForExistence(timeout: 20))
        let completed = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == 'PASS' OR label BEGINSWITH 'FAIL:'"), object: status)
        XCTAssertEqual(XCTWaiter.wait(for: [completed], timeout: 90), .completed)
        XCTAssertEqual(status.label, "PASS")
        app.terminate()
    }
}
