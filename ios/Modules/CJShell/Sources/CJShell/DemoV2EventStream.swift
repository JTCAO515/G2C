import Foundation
import CJMessageHTTP

/// #702 sequence-cursor fixture. The original RUN byte-offset stream is separate.
/// Transport EOF has no user-visible meaning; only protected events carry status.
struct DemoV2EventStream {
    enum Failure: Error, Equatable {
        case invalidConfiguration, invalidFrame, invalidSequence, responseTooLarge, incompleteFrame
    }

    private let receipt: DemoV2Dialogue.Receipt
    private let maximumWireBytes: Int
    private var wireBytes = 0
    private var line: [UInt8] = []
    private var eventName: String?
    private var sequence: Int64?
    private var dataLines: [String] = []
    private var confirmedSequence: Int64?

    var lastEventID: String? { confirmedSequence.map { String($0) } }

    init(receipt: DemoV2Dialogue.Receipt, maximumWireBytes: Int, resumingAfter: Int64? = nil) throws {
        guard maximumWireBytes > 0, resumingAfter.map({ $0 >= 0 }) ?? true else { throw Failure.invalidConfiguration }
        self.receipt = receipt
        self.maximumWireBytes = maximumWireBytes
        self.confirmedSequence = resumingAfter
    }

    /// Commit the cursor only if all events returned to the caller were verified.
    /// A malformed later frame in this chunk does not skip an undisplayed event.
    mutating func append(_ bytes: Data) throws -> [DemoV2Dialogue.Event] {
        var candidate = self
        let events = try candidate.consume(bytes)
        self = candidate
        return events
    }

    func finish() throws {
        guard line.isEmpty, sequence == nil, eventName == nil, dataLines.isEmpty else { throw Failure.incompleteFrame }
    }

    private mutating func consume(_ bytes: Data) throws -> [DemoV2Dialogue.Event] {
        guard bytes.count <= maximumWireBytes - wireBytes else { throw Failure.responseTooLarge }
        wireBytes += bytes.count
        var events: [DemoV2Dialogue.Event] = []
        for byte in bytes {
            if byte != 10 {
                line.append(byte)
                continue
            }
            if line.last == 13 { line.removeLast() }
            guard let value = String(bytes: line, encoding: .utf8) else { throw Failure.invalidFrame }
            line.removeAll(keepingCapacity: true)
            if value.isEmpty {
                if sequence != nil || eventName != nil || !dataLines.isEmpty { events.append(try completeFrame()) }
                continue
            }
            if value.hasPrefix(":") { continue }
            guard let colon = value.firstIndex(of: ":") else { throw Failure.invalidFrame }
            var content = value[value.index(after: colon)...]
            if content.first == " " { content = content.dropFirst() }
            switch value[..<colon] {
            case "id":
                guard sequence == nil, !content.isEmpty,
                      content.utf8.allSatisfy({ (48...57).contains($0) }),
                      let id = Int64(content), id > 0, String(id) == content else { throw Failure.invalidSequence }
                sequence = id
            case "event":
                guard eventName == nil, !content.isEmpty else { throw Failure.invalidFrame }
                eventName = String(content)
            case "data":
                dataLines.append(String(content))
            default:
                throw Failure.invalidFrame
            }
        }
        return events
    }

    private mutating func completeFrame() throws -> DemoV2Dialogue.Event {
        guard let sequence, !dataLines.isEmpty else { throw Failure.invalidFrame }
        if let previous = confirmedSequence {
            guard previous < Int64.max, sequence == previous + 1 else { throw Failure.invalidSequence }
        }
        let data = Data(dataLines.joined(separator: "\n").utf8)
        try validateUnambiguousJSON(data)
        let event = try JSONDecoder().decode(DemoV2Dialogue.Event.self, from: data)
        try event.checkOriginal(receipt)
        confirmedSequence = sequence
        self.sequence = nil
        eventName = nil
        dataLines.removeAll(keepingCapacity: true)
        return event
    }
}
