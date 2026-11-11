#if os(iOS)
import SwiftUI

struct LioTripHistoryView: View {
    let plan: LioTripPlan
    let language: LioLanguage
    let canUndo: Bool

    var body: some View {
        List {
            Group {
                if let current = plan.current {
                    Section(language.text("Current plan", "现在的安排")) {
                        Text(current.title).font(.headline)
                        LioTripDays(itinerary: current, language: language) { _ in }
                        if let target = plan.target {
                            Button(language.text("Go back to the previous plan", "恢复上一次安排")) {
                                Task { await plan.undo(target) }
                            }
                            .disabled(!canUndo || plan.busy || plan.pending)
                            .accessibilityIdentifier("lio.trip.undo")
                        }
                    }
                } else if plan.loaded && plan.notice == nil {
                    Text(language.text("No trips yet", "还没有行程"))
                }
                if plan.pending {
                    Text(language.text("Waiting for the trip to update…", "正在等行程更新…"))
                        .accessibilityIdentifier("lio.trip.undo.waiting")
                }
                if let notice = plan.notice {
                    Text(notice.text(language))
                    Button(language.text("Try again", "再试一次")) {
                        Task { await plan.reload(for: plan.requestedCard) }
                    }
                    .disabled(plan.busy)
                }
                if !plan.previous.isEmpty {
                    Section(language.text("Previous plans", "此前的安排")) {
                        ForEach(plan.previous.indices, id: \.self) { index in
                            let itinerary = plan.previous[index]
                            DisclosureGroup {
                                LioTripDays(itinerary: itinerary, language: language) { _ in }
                            } label: {
                                Text(index == 0 ? language.text("Previous plan", "上一次安排")
                                     : language.text("Earlier plan \(index + 1)", "更早的安排 \(index + 1)"))
                            }
                        }
                        if let nextBefore = plan.nextBefore {
                            Button(language.text("Earlier plans", "更早的安排")) {
                                Task { await plan.loadEarlier(nextBefore) }
                            }
                            .disabled(plan.busy)
                        }
                    }
                }
                if plan.busy { ProgressView() }
            }
            .lioRow()
        }
        .lioPage()
        .navigationTitle(language.text("Previous plans", "此前的安排"))
    }
}
#endif
