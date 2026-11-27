import CJMessageHTTP
import Foundation
import Observation

/// #1994 (58.1 T-1, App): the Undo button on the receipt of an automatic save, behind `G2CAutosaveUndoEnabled` (off unless
/// the build says YES). It needs `LIO-answer-rich.1` (`G2CAnswerRichEnabled`): the receipt is part of it. Off, the receipt
/// line has no button, exactly as `G2CAutosaveNoticeEnabled` alone shows it. The server's own switch
/// (`CJ_LIO_TRIP_AUTOSAVE`) decides which accounts get a receipt and whether its undo is available; the App shows a
/// button only for an undo the server says is `available`.
enum LioAutosaveUndoFeature {
    static let infoKey = "G2CAutosaveUndoEnabled"
    static func enabled(infoValue: Any?) -> Bool { infoValue as? String == "YES" }

    /// This switch alone.
    static var enabledInBuild: Bool { enabled(infoValue: Bundle.main.object(forInfoDictionaryKey: infoKey)) }

    /// The whole feature: the switch and rich answers.
    static func active(undo: Bool, rich: Bool) -> Bool { undo && rich }
    static var activeInBuild: Bool { active(undo: enabledInBuild, rich: LioAnswerRichFeature.enabledInBuild) }
}

/// Whether the receipt of an automatic save is read at all: with rich answers, and with either the notice or the undo.
enum LioAutosaveReceiptFeature {
    static func reads(notice: Bool, undo: Bool, rich: Bool) -> Bool { rich && (notice || undo) }
}

/// What the traveller sees of one undo while it runs or after it ended, kept for the life of the screen. The server's own
/// reading of the receipt (`undo.state`, computed at every read) always wins over this: it only fills the time before
/// that reading arrives, after the server said the undo is committed.
@MainActor @Observable
final class LioAutosaveUndo {
    enum Phase: Equatable, Sendable {
        /// The request is out.
        case undoing
        /// The answer was not known; the same action is being asked about.
        case confirming
        /// The server said it committed the undo.
        case undone
        /// The server said the trip changed since the save.
        case superseded
        /// The server refused: the time is over.
        case expired
        /// Nothing was written, or nothing could be learned: the traveller may try again (same action id).
        case failed
    }

    /// Pauses before asking again after an answer that was not known.
    static let confirmDelays: [Duration] = [.seconds(2), .seconds(5), .seconds(15)]

    @ObservationIgnored private let client: LioTripUndoClient
    @ObservationIgnored private let pause: @Sendable (Duration) async -> Void
    /// By the id of the save (`receipt.actionID`), which is stable across reads.
    private(set) var phases: [String: Phase] = [:]

    init(client: LioTripUndoClient, pause: @escaping @Sendable (Duration) async -> Void = { try? await Task.sleep(for: $0) }) {
        self.client = client
        self.pause = pause
    }

    func phase(of receipt: LioTimelineWire.TripReceipt) -> Phase? { phases[receipt.actionID] }

    /// The end of the undo window, or nil when the receipt carries none.
    static func deadline(of receipt: LioTimelineWire.TripReceipt) -> Date? {
        guard let until = receipt.undo?.until else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.date(from: until)
    }

    /// The button shows only for a saved receipt whose undo the server calls `available`, whose time is not over on this
    /// device's clock, and that is not being undone or already settled. (The server decides in the end: a device clock that
    /// is wrong only changes when the button shows, never whether an undo is allowed.)
    func offers(_ receipt: LioTimelineWire.TripReceipt, at date: Date) -> Bool {
        guard receipt.status == .saved, receipt.undo?.state == .available, receipt.undo?.target != nil,
              let deadline = Self.deadline(of: receipt), date < deadline else { return false }
        switch phases[receipt.actionID] {
        case nil, .failed: return true
        case .undoing, .confirming, .undone, .superseded, .expired: return false
        }
    }

    /// Undo this receipt's save. Nothing is sent unless `offers` says so, and an action already being sent is not sent again.
    /// `refresh` runs once the server has answered for good (committed, or no longer undoable): it re-reads the timeline
    /// and the trip through the readers the App already has, so what shows afterwards is what the server says.
    func undo(_ receipt: LioTimelineWire.TripReceipt, conversationID: String?, at date: Date = .now,
              refresh: @MainActor () async -> Void) async {
        guard offers(receipt, at: date), let conversationID,
              let request = LioTripUndoWire.Request(receipt: receipt, conversationID: conversationID),
              !client.isSending(request.actionID) else { return }
        let id = receipt.actionID, previous = phases[id]
        phases[id] = .undoing
        var outcome = await client.undo(request)
        var delays = Self.confirmDelays[...]
        while outcome == .unknown, let delay = delays.popFirst() {
            phases[id] = .confirming
            await pause(delay)
            guard !Task.isCancelled else { break }
            outcome = await client.confirm(request)
        }
        switch outcome {
        case .undone: phases[id] = .undone
        case .superseded: phases[id] = .superseded
        case .expired: phases[id] = .expired
        case .notDone, .unknown: phases[id] = .failed
        case .inFlight:
            phases[id] = previous
            return
        }
        if phases[id] != .failed { await refresh() }
    }
}
