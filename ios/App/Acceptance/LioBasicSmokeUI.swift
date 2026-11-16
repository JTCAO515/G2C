import CJStrictJSON
import Darwin
import Foundation
import XCTest

// External XCTest controller only. The target App is installed separately from
// its clean, pinned Beta build; this runner adds no hooks to the App itself.
private enum CommandJSON: StrictJSONPolicy {
    enum Failure: Error { case invalidCommand }
    static let failure = Failure.invalidCommand
    static let requiresObjectRoot = true
}

@MainActor final class LioBasicSmokeUI: XCTestCase {
    private struct Command: Decodable {
        let id: String
        let kind: String
        let bundle: String
        let language: String?
        let identifier: String?
        let index: Int?
        let text: String?
        let privateInputPath: String?
        let startsAt: String?
        let endsAt: String?
    }

    func testDriveOrdinaryHome() async throws {
        continueAfterFailure = false
        let directory = URL(fileURLWithPath: "__COMMAND_DIRECTORY__", isDirectory: true)
        try Data("ready".utf8).write(to: directory.appendingPathComponent("ready"), options: .withoutOverwriting)
        var sequence = 0
        while true {
            let stem = String(format: "%05d", sequence)
            let input = directory.appendingPathComponent(stem + ".request.json")
            if !FileManager.default.fileExists(atPath: input.path) {
                try await Task.sleep(for: .milliseconds(100))
                continue
            }
            let bytes = try Data(contentsOf: input)
            guard bytes.count <= 1_048_576 else { throw CommandJSON.failure }
            var json = StrictJSONReader<CommandJSON>(bytes: Array(bytes)); try json.check()
            let command = try JSONDecoder().decode(Command.self, from: bytes)
            let intent = directory.appendingPathComponent(stem + ".started")
            guard !FileManager.default.fileExists(atPath: intent.path) else {
                XCTFail("A previous UI command has an unresolved execution record")
                return
            }
            try Data().write(to: intent, options: .withoutOverwriting)
            let app = XCUIApplication(bundleIdentifier: command.bundle)
            var result: [String: Any] = ["id": command.id, "kind": command.kind,
                "started_uptime": ProcessInfo.processInfo.systemUptime]
            func requireActionWindow() throws {
                var calendar = Calendar(identifier: .gregorian)
                calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
                let now = Date()
                guard (8..<23).contains(calendar.component(.hour, from: now)) else { throw CommandJSON.failure }
                if command.bundle == "space.go2china.app" {
                    func boundary(_ raw: String?) -> Date? {
                        guard let raw else { return nil }
                        let formatter = ISO8601DateFormatter()
                        if raw.contains(".") { formatter.formatOptions.insert(.withFractionalSeconds) }
                        return formatter.date(from: raw)
                    }
                    guard let start = boundary(command.startsAt), let end = boundary(command.endsAt),
                          start <= now, now < end else { throw CommandJSON.failure }
                }
            }
            do {
                if command.kind != "snapshot" && command.kind != "stop" {
                    try requireActionWindow()
                }
                switch command.kind {
                case "launch":
                    if let language = command.language {
                        app.launchArguments = ["-cj.ui.language.v1", language == "zh" ? "zh-Hans" : "en"]
                    }
                    try requireActionWindow(); app.launch()
                case "activate": try requireActionWindow(); app.activate()
                case "terminate": try requireActionWindow(); app.terminate()
                case "background": try requireActionWindow(); XCUIDevice.shared.press(.home)
                case "tap":
                    let identifier = try XCTUnwrap(command.identifier)
                    let target = app.buttons.matching(identifier: identifier).element(boundBy: command.index ?? 0)
                    guard target.exists, target.isEnabled, target.isHittable else { throw CommandJSON.failure }
                    try requireActionWindow(); target.tap()
                case "type":
                    let identifier = try XCTUnwrap(command.identifier)
                    let field = app.descendants(matching: .any).matching(identifier: identifier).firstMatch
                    guard field.exists, field.isHittable else { throw CommandJSON.failure }
                    try requireActionWindow(); field.tap()
                    try requireActionWindow(); field.typeText(try XCTUnwrap(command.text))
                case "select_all":
                    let field = app.descendants(matching: .any).matching(identifier: "lio.composer").firstMatch
                    guard field.exists, field.isHittable else { throw CommandJSON.failure }
                    try requireActionWindow(); field.press(forDuration: 1.2)
                    let select = app.descendants(matching: .any).matching(
                        NSPredicate(format: "label IN %@", ["Select All", "全选"])).firstMatch
                    guard select.waitForExistence(timeout: 3), select.isHittable else { throw CommandJSON.failure }
                    try requireActionWindow(); select.tap()
                case "private_invite":
                    let field = app.secureTextFields["demo.invite.code"]
                    guard field.exists, field.isHittable else { throw CommandJSON.failure }
                    let path = try XCTUnwrap(command.privateInputPath)
                    let url = URL(fileURLWithPath: path)
                    guard url.standardizedFileURL.path == url.resolvingSymlinksInPath().path else { throw CommandJSON.failure }
                    try requireActionWindow()
                    let fd = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
                    guard fd >= 0 else { throw CommandJSON.failure }
                    defer { close(fd) }
                    var info = stat()
                    guard fstat(fd, &info) == 0, info.st_mode & S_IFMT == S_IFREG,
                          info.st_uid == getuid(), info.st_nlink == 1,
                          info.st_mode & 0o777 == 0o600, info.st_size > 0, info.st_size <= 4096 else {
                        throw CommandJSON.failure
                    }
                    let data = try FileHandle(fileDescriptor: fd, closeOnDealloc: false).read(upToCount: 4097) ?? Data()
                    guard !data.isEmpty, data.count <= 4096, data.allSatisfy({ (0x21...0x7e).contains($0) }),
                          let value = String(data: data, encoding: .utf8) else { throw CommandJSON.failure }
                    try requireActionWindow(); field.tap()
                    try requireActionWindow(); field.typeText(value)
                    // Never return the input or any value derived from it.
                case "swipe_up": try requireActionWindow(); app.swipeUp(velocity: .slow)
                case "swipe_down": try requireActionWindow(); app.swipeDown(velocity: .slow)
                case "snapshot", "stop": break
                default: throw CommandJSON.failure
                }
                if command.kind == "snapshot" {
                    let snapshot = try app.snapshot()
                    var nodes: [[String: Any]] = []
                    func visit(_ node: any XCUIElementSnapshot, depth: Int) {
                        let frame = node.frame.isNull || node.frame.isInfinite ? CGRect.zero : node.frame
                        nodes.append(["depth": depth, "identifier": node.identifier, "label": node.label,
                            "value": node.value as? String ?? "", "type": node.elementType.rawValue,
                            "progress_indicator": node.elementType == .progressIndicator,
                            "enabled": node.isEnabled, "selected": node.isSelected,
                            "frame": [frame.minX, frame.minY, frame.width, frame.height]])
                        node.children.forEach { visit($0, depth: depth + 1) }
                    }
                    visit(snapshot, depth: 0)
                    result["nodes"] = nodes
                    let image = directory.appendingPathComponent(stem + ".png")
                    try app.screenshot().pngRepresentation.write(to: image, options: .atomic)
                    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: image.path)
                    result["screenshot"] = image.lastPathComponent
                }
                result["ok"] = true
            } catch {
                // A missing result for a tap is UNKNOWN, never permission to repeat it.
                result["ok"] = false
                result["error"] = "native_UI_action_unavailable"
            }
            result["finished_uptime"] = ProcessInfo.processInfo.systemUptime
            let output = directory.appendingPathComponent(stem + ".response.json")
            try JSONSerialization.data(withJSONObject: result, options: .sortedKeys).write(to: output, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: output.path)
            sequence += 1
            if command.kind == "stop" { return }
        }
    }
}
