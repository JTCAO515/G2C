#if os(iOS)
import CJMessageHTTP
import SwiftUI

struct LioTripHistoryView: View {
    let client: LioTripHistoryClient
    let language: LioLanguage
    let onCurrentPlan: (LioItinerary?) -> Void
    @State private var current: LioItinerary?
    @State private var previous: [LioItinerary] = []
    @State private var target: LioTripHistoryWire.Target?
    @State private var nextBefore: String?
    @State private var loaded = false
    @State private var busy = false
    @State private var pending = false
    @State private var notice: String?
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        List {
            if let current {
                Section(language.text("Current plan", "现在的安排")) {
                    Text(current.title).font(.headline)
                    LioTripDays(itinerary: current, language: language) { _ in }
                    if let target {
                        Button(language.text("Go back to the previous plan", "恢复上一次安排")) {
                            Task { await undo(target) }
                        }
                        .disabled(busy || pending)
                        .accessibilityIdentifier("lio.trip.undo")
                    }
                }
            } else if loaded && notice == nil {
                Text(language.text("No trips yet", "还没有行程"))
            }
            if pending {
                Text(language.text("Waiting for the trip to update…", "正在等行程更新…"))
                    .accessibilityIdentifier("lio.trip.undo.waiting")
            }
            if let notice {
                Text(notice)
                Button(language.text("Try again", "再试一次")) {
                    Task { await reload() }
                }
                .disabled(busy)
            }
            if !previous.isEmpty {
                Section(language.text("Previous plans", "此前的安排")) {
                    ForEach(previous.indices, id: \.self) { index in
                        let itinerary = previous[index]
                        DisclosureGroup {
                            LioTripDays(itinerary: itinerary, language: language) { _ in }
                        } label: {
                            Text(index == 0 ? language.text("Previous plan", "上一次安排")
                                 : language.text("Earlier plan \(index + 1)", "更早的安排 \(index + 1)"))
                        }
                    }
                    if let nextBefore {
                        Button(language.text("Earlier plans", "更早的安排")) {
                            Task { await loadEarlier(nextBefore) }
                        }
                        .disabled(busy)
                    }
                }
            }
            if busy { ProgressView() }
        }
        .navigationTitle(language.text("Previous plans", "此前的安排"))
        .task { await reload() }
        .task(id: pending && scenePhase == .active) {
            guard pending, scenePhase == .active else { return }
            await awaitUndo()
        }
    }

    private func reload() async {
        busy = true
        defer { busy = false }
        target = nil
        notice = nil
        do {
            let waiting = try client.hasPendingUndo()
            do {
                let page = try await client.history()
                try Task.checkCancellation()
                current = page.current.map(LioItinerary.init)
                onCurrentPlan(current)
                previous = page.history.map(LioItinerary.init)
                target = page.undoTarget
                nextBefore = page.nextBefore
                loaded = true
            } catch is CancellationError {
                return
            } catch {
                notice = language.text("Couldn’t show the latest plan.", "暂时无法显示最新安排。")
            }
            pending = waiting
        } catch {
            notice = language.text("Couldn’t show the latest plan.", "暂时无法显示最新安排。")
        }
    }

    private func loadEarlier(_ before: String) async {
        guard !busy, before == nextBefore else { return }
        busy = true
        defer { busy = false }
        do {
            let page = try await client.history(before: before)
            try Task.checkCancellation()
            guard nextBefore == before else { return }
            previous.append(contentsOf: page.history.map(LioItinerary.init))
            nextBefore = page.nextBefore
        } catch is CancellationError {
            return
        } catch {
            notice = language.text("Couldn’t show earlier plans.", "暂时无法显示更早的安排。")
        }
    }

    private func undo(_ target: LioTripHistoryWire.Target) async {
        guard !busy, !pending, self.target == target else { return }
        busy = true
        defer { busy = false }
        notice = nil
        do {
            switch try await client.undo(target) {
            case .pending:
                pending = true
            case .committed:
                await reload()
            case .changed:
                await reload()
                if notice == nil {
                    notice = language.text("The trip changed. Here’s the latest plan.", "行程已有变化，请查看最新安排。")
                }
            }
        } catch is CancellationError {
            return
        } catch {
            self.target = nil
            notice = language.text("Couldn’t update the trip right now.", "暂时无法更新行程。")
        }
    }

    private func awaitUndo() async {
        while !Task.isCancelled {
            do {
                let state = try await client.reconcileUndo()
                if state == .committed || state == nil {
                    await reload()
                    return
                }
            } catch is CancellationError {
                return
            } catch {
                notice = language.text("Couldn’t show the latest plan.", "暂时无法显示最新安排。")
            }
            do {
                try await Task.sleep(for: .seconds(5))
            } catch {
                return
            }
        }
    }
}
#endif
