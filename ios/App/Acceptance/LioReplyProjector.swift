import CryptoKit
import Foundation
@testable import CJLioUser

@main struct LioReplyProjector {
    static func sha(_ bytes: Data) -> String { SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined() }
    @MainActor static func run() throws {
        let bytes = FileHandle.standardInput.readDataToEndOfFile()
        guard bytes.count <= 5_000_000,
              let input = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              input["version"] as? String == "LIO-reply-projection-request.1",
              let app = input["app"] as? [String: Any],
              app["source_commit"] as? String == ProjectorPin.source,
              app["renderer_source_sha256"] as? String == ProjectorPin.renderer,
              let raw = input["raw_utf8"] as? String,
              let digest = input["input_sha256"] as? String, digest == sha(Data(raw.utf8)) else {
            throw ProjectorFailure.invalidInput
        }
        let rendered = LioReplyMarkdown.render(raw).map { String($0.characters) }
        let text = rendered ?? ""
        let output: [String: Any] = [
            "version": "LIO-reply-projection.1", "app": app,
            "renderer_source_sha256": ProjectorPin.renderer,
            "input_sha256": digest, "rejected": rendered == nil,
            "rendered_utf8": text, "rendered_sha256": sha(Data(text.utf8)),
            "projection_environment": ["platform": "macOS", "version": ProcessInfo.processInfo.operatingSystemVersionString]
        ]
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys]))
        FileHandle.standardOutput.write(Data([10]))
    }
    @MainActor static func main() {
        do { try run() }
        catch {
            FileHandle.standardError.write(Data("Projection unavailable: invalid input or source binding.\n".utf8))
            exit(2)
        }
    }
}
private enum ProjectorFailure: Error { case invalidInput }
