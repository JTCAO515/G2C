import XCTest

@MainActor final class LioReadStateUITests: XCTestCase {
    func testUnavailableAndLoadedEmptyStatesHaveDistinctActualAXInBothLanguages() throws {
        continueAfterFailure = false
        for chinese in [false, true] {
            for unavailable in [true, false] {
                let app = XCUIApplication(bundleIdentifier: "space.go2china.read-state.acceptance")
                app.launchArguments = ["--lio-preview", "-cj.ui.language.v1", chinese ? "zh-Hans" : "en"]
                    + (unavailable ? ["--read-stream-ended"] : [])
                app.launch()
                if unavailable {
                    XCTAssertTrue(app.buttons["lio.read.retry"].waitForExistence(timeout: 8))
                    XCTAssertFalse(app.buttons["lio.example.0"].exists)
                } else {
                    XCTAssertTrue(app.buttons["lio.example.0"].waitForExistence(timeout: 8))
                    XCTAssertFalse(app.buttons["lio.read.retry"].exists)
                }
                let root = try app.snapshot()
                var nodes = [[String: Any]]()
                func visit(_ node: any XCUIElementSnapshot, depth: Int) {
                    nodes.append(["identifier": node.identifier, "label": node.label,
                        "value": node.value as? String ?? "", "enabled": node.isEnabled,
                        "depth": depth, "type": node.elementType.rawValue,
                        "progress_indicator": node.elementType == .progressIndicator || node.elementType == .activityIndicator])
                    node.children.forEach { visit($0, depth: depth + 1) }
                }
                visit(root, depth: 0)
                let data = try JSONSerialization.data(withJSONObject: ["scope": "L0_native_fixture_no_network", "nodes": nodes])
                let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
                attachment.name = "read-state-\(unavailable ? "unavailable" : "empty")-\(chinese ? "zh" : "en")"
                attachment.lifetime = .keepAlways; add(attachment)
                app.terminate()
            }
        }
    }
}
