import Foundation

/// Ephemeral received text, never a formal RUN snapshot or a persisted recovery authority.
public struct RunStreamProgress: Sendable, CustomStringConvertible, CustomDebugStringConvertible, CustomReflectable {
    public let text: String
    public let status: String?
    public var byteOffset: Int { text.utf8.count }
    public var description: String { "<redacted run stream>" }
    public var debugDescription: String { description }
    public var customMirror: Mirror { Mirror(self, children: [:]) }
}

/// Bounded parser for the existing /v1/run-events dialect. Offsets count UTF-8 bytes,
/// not Swift characters. A truncated frame or EOF without terminal status is unknown.
struct RunEventParser {
    private let maximumTextBytes: Int
    private let maximumWireBytes: Int
    private var wireBytes = 0
    private var line: [UInt8] = []
    private var event: String?
    private var eventID: String?
    private var data: String?
    private(set) var progress: RunStreamProgress
    private(set) var terminal = false

    init(text: String, maximumTextBytes: Int, maximumWireBytes: Int) throws {
        guard maximumTextBytes > 0, maximumWireBytes > 0, text.utf8.count <= maximumTextBytes else {
            throw RunDisplayFailure.invalidConfiguration
        }
        self.maximumTextBytes = maximumTextBytes; self.maximumWireBytes = maximumWireBytes
        progress = RunStreamProgress(text: text, status: nil)
    }

    mutating func append(_ bytes: ArraySlice<UInt8>) throws -> RunStreamProgress? {
        guard bytes.count <= maximumWireBytes - wireBytes else { throw RunDisplayFailure.invalidResponse }
        wireBytes += bytes.count
        var update: RunStreamProgress?
        for byte in bytes {
            if byte != 10 { line.append(byte); continue }
            if line.last == 13 { line.removeLast() }
            guard let value = String(bytes: line, encoding: .utf8) else { throw RunDisplayFailure.invalidResponse }
            line.removeAll(keepingCapacity: true)
            if value.isEmpty {
                if event == nil && eventID == nil && data == nil { continue }
                try finishEvent(); update = progress
            } else if !value.hasPrefix(":") {
                guard !terminal, let colon = value.firstIndex(of: ":") else { throw RunDisplayFailure.invalidResponse }
                let field = String(value[..<colon])
                var content = value[value.index(after: colon)...]
                if content.first == " " { content = content.dropFirst() }
                switch field {
                case "event": guard event == nil else { throw RunDisplayFailure.invalidResponse }; event = String(content)
                case "id": guard eventID == nil else { throw RunDisplayFailure.invalidResponse }; eventID = String(content)
                case "data": guard data == nil else { throw RunDisplayFailure.invalidResponse }; data = String(content)
                default: throw RunDisplayFailure.invalidResponse
                }
            }
        }
        return update
    }

    private mutating func finishEvent() throws {
        guard !terminal, let event, let eventID, let data,
              (1...12).contains(eventID.utf8.count), eventID.utf8.allSatisfy({ (48...57).contains($0) }),
              let offset = Int(eventID) else { throw RunDisplayFailure.invalidResponse }
        let bytes = Data(data.utf8)
        var strict = StrictRunJSON(bytes: Array(bytes)); try strict.check()
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any], object.count == 1 else {
            throw RunDisplayFailure.invalidResponse
        }
        if event == "delta" {
            guard let text = object["text"] as? String, !text.isEmpty,
                  text.utf8.count <= maximumTextBytes - progress.byteOffset,
                  offset == progress.byteOffset + text.utf8.count else { throw RunDisplayFailure.inconsistentSnapshot }
            progress = RunStreamProgress(text: progress.text + text, status: progress.status)
        } else if event == "status" {
            guard let status = object["status"] as? String,
                  ["queued", "running", "completed", "failed", "cancelled", "context_invalid", "unknown", "unavailable"].contains(status),
                  offset == progress.byteOffset,
                  status != "queued" || (progress.text.isEmpty && progress.status != "running") else {
                throw RunDisplayFailure.invalidResponse
            }
            // The producer emits unavailable after its protected read stops admitting
            // the source. Hide previously received private text, like a refused GET.
            guard status != "unavailable" else { throw RunDisplayFailure.rejected(status: 503) }
            progress = RunStreamProgress(text: progress.text, status: status)
            terminal = status != "queued" && status != "running"
        } else { throw RunDisplayFailure.invalidResponse }
        self.event = nil; self.eventID = nil; self.data = nil
    }

    func finish() throws {
        guard terminal, line.isEmpty, event == nil, eventID == nil, data == nil else {
            throw RunDisplayFailure.unavailable
        }
    }
}
