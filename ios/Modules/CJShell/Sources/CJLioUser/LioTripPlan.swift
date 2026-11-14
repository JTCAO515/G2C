import CJMessageHTTP
import Foundation
import Observation

struct LioTripCard: Equatable, Sendable {
    let turnID: Data
    let itinerary: LioItinerary
}

@MainActor
protocol LioTripPlanning {
    func history(before: String?) async throws -> LioTripHistoryWire.Page
    func hasPendingUndo() throws -> Bool
    func undo(_ target: LioTripHistoryWire.Target) async throws -> LioTripHistoryClient.UndoState
    func reconcileUndo() async throws -> LioTripHistoryClient.UndoState?
}

extension LioTripHistoryClient: LioTripPlanning {}

@MainActor @Observable
final class LioTripPlan {
    enum Notice {
        case latestUnavailable, earlierUnavailable, changed, undoUnavailable

        func text(_ language: LioLanguage) -> String {
            switch self {
            case .latestUnavailable: language.text("Couldn’t show the latest plan.", "暂时无法显示最新安排。")
            case .earlierUnavailable: language.text("Couldn’t show earlier plans.", "暂时无法显示更早的安排。")
            case .changed: language.text("The trip changed. Here’s the latest plan.", "行程已有变化，请查看最新安排。")
            case .undoUnavailable: language.text("Couldn’t update the trip right now.", "暂时无法更新行程。")
            }
        }
    }

    private let client: any LioTripPlanning
    private var reading = false
    private var readingEarlier = false
    private var writing = false
    private var request = UUID()
    private(set) var requestedCard: LioTripCard?
    private var presentedCard: LioTripCard?
    private(set) var current: LioItinerary?
    private(set) var previous: [LioItinerary] = []
    private(set) var target: LioTripHistoryWire.Target?
    private(set) var nextBefore: String?
    private(set) var loaded = false
    private(set) var pending = false
    private(set) var notice: Notice?
    var busy: Bool { reading || readingEarlier || writing }

    init(client: any LioTripPlanning) { self.client = client }

    func current(for card: LioTripCard?) -> LioItinerary? {
        guard card == presentedCard else { return nil }
        return current
    }

    func current(in card: LioTripCard) -> LioItinerary? {
        guard let plan = current(for: card),
              Data(plan.id.utf8) == Data(card.itinerary.id.utf8) else { return nil }
        return plan
    }

    func reload(for card: LioTripCard?) async {
        let id = UUID()
        request = id
        requestedCard = card
        reading = true
        target = nil
        notice = nil
        var waiting = pending
        defer {
            if request == id {
                reading = false
                pending = waiting
            }
        }
        do {
            waiting = try client.hasPendingUndo()
            let page = try await client.history(before: nil)
            try Task.checkCancellation()
            guard request == id else { return }
            current = page.current.map(LioItinerary.init)
            previous = page.history.map(LioItinerary.init)
            target = page.undoTarget
            nextBefore = page.nextBefore
            presentedCard = card
            loaded = true
        } catch is CancellationError {
            return
        } catch {
            if request == id { notice = .latestUnavailable }
        }
    }

    func loadEarlier(_ before: String) async {
        guard !busy, before == nextBefore else { return }
        let id = request
        readingEarlier = true
        defer { readingEarlier = false }
        do {
            let page = try await client.history(before: before)
            try Task.checkCancellation()
            guard request == id else { return }
            previous.append(contentsOf: page.history.map(LioItinerary.init))
            nextBefore = page.nextBefore
        } catch is CancellationError {
            return
        } catch {
            if request == id { notice = .earlierUnavailable }
        }
    }

    func undo(_ target: LioTripHistoryWire.Target) async {
        guard !busy, !pending, self.target == target else { return }
        writing = true
        defer { writing = false }
        notice = nil
        do {
            switch try await client.undo(target) {
            case .pending:
                pending = true
            case .committed:
                await reload(for: requestedCard)
            case .changed:
                await reload(for: requestedCard)
                if notice == nil { notice = .changed }
            }
        } catch {
            self.target = nil
            do { pending = try client.hasPendingUndo() }
            catch { pending = true }
            if !pending { notice = .undoUnavailable }
        }
    }

    func awaitUndo() async {
        while !Task.isCancelled {
            do {
                let state = try await client.reconcileUndo()
                if state == .committed || state == nil {
                    await reload(for: requestedCard)
                    return
                }
            } catch is CancellationError {
                return
            } catch {
                notice = .latestUnavailable
            }
            do { try await Task.sleep(for: .seconds(5)) } catch { return }
        }
    }
}
