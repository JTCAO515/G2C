#if os(iOS)
import SwiftUI
import CJTripClient

private extension ShellLanguage {
    var tripLanguage: TripLanguage { self == .english ? .english : .simplifiedChinese }
}

struct TripShell: View {
    @Bindable var state: ShellState
    let host: TripContainerHost
    @State private var manualEntry: ManualPreviewEntry?
    @Environment(\.scenePhase) private var scenePhase
    private var language: ShellLanguage { state.language }
    var body: some View {
        let action = host.captureAction()
        NavigationStack(path: $state.tripPath) {
            List {
                if let presentation = host.presentation {
                    Section(language.text("Formal trips", "正式行程")) {
                        TripContainerLoadLabel(state: presentation.listState, language: language)
                        if presentation.listState == .loaded && presentation.trips.isEmpty {
                            Text(language.text("No trips returned", "暂无行程"))
                        }
                        ForEach(presentation.trips, id: \.trip_id) { trip in
                            Button {
                                if host.selectTrip(trip.trip_id, context: action) { state.tripPath.append(.detail) }
                            } label: {
                                VStack(alignment: .leading) {
                                    Text(trip.document.title)
                                    Text(language.text("Current version \(trip.version)", "当前版本 \(trip.version)")).font(.caption)
                                }
                            }.disabled(action == nil)
                        }
                        Button(language.text("Refresh trips", "刷新行程")) {
                            guard let work = host.prepareTrips(context: action) else { return }
                            Task { await host.perform(work) }
                        }.disabled(action == nil)
                        if presentation.next != nil {
                            Button(language.text("Load next page", "读取下一页")) {
                                guard let work = host.prepareTrips(context: action, more: true) else { return }
                                Task { await host.perform(work) }
                            }.disabled(action == nil)
                        }
                        Text(language.text("Live pages may change while browsing.", "浏览期间，分页内容可能更新。"))
                            .font(.caption)
                    }
                    Section(language.text("Current context", "当前上下文")) {
                        if let id = host.contextTripID {
                            Button(language.text("View selected trip", "查看选中行程")) {
                                if host.selectTrip(id, context: action) { state.tripPath.append(.detail) }
                            }.disabled(action == nil)
                        }
                        if host.contextProposalID != nil {
                            NavigationLink(language.text("View current draft", "查看当前草稿"), value: TripRoute.proposal)
                        } else {
                            Text(language.text("No draft is selected.", "当前未选择草稿。"))
                        }
                    }
                    Section(language.text("Original actions", "原动作")) {
                        TripContainerLoadLabel(state: presentation.pendingState, language: language)
                        if presentation.pendingState == .loaded && presentation.pendingActions.isEmpty {
                            Text(language.text("No original actions found.", "未发现原动作。"))
                        }
                        ForEach(presentation.pendingActions, id: \.actionID) { original in
                            Button {
                                if host.selectPending(original.actionID, context: action) { state.tripPath.append(.originalAction) }
                            } label: {
                                VStack(alignment: .leading) {
                                    Text(original.proposal.document.title)
                                    Text(original.actionID).font(.caption)
                                }
                            }.disabled(action == nil || presentation.pendingState != .loaded)
                        }
                        Button(language.text("Read original actions", "读取原动作")) { host.loadPending(context: action) }
                            .disabled(action == nil)
                    }
                    if host.isSynthetic { Text(language.text("Synthetic test data", "合成测试数据")).font(.caption) }
                } else {
                    Text(language.text("Trips are not connected. No records have been loaded.", "行程尚未连接，未读取任何记录。"))
                }
            }
            .navigationTitle(ShellTab.trips.title(language))
            .sheet(item: $manualEntry) { entry in
                ManualPreviewContainerView(host: host, entry: entry, language: language)
            }
            .onAppear { host.setManualForeground(scenePhase == .active) }
            .onChange(of: scenePhase) { _, phase in host.setManualForeground(phase == .active) }
            .onChange(of: host.manualPreviewIdentity) { _, id in
                if id == nil, host.manualPreviewIdentity == nil { manualEntry = nil }
            }
            .onDisappear { host.setManualForeground(false) }
            .navigationDestination(for: TripRoute.self) { route in
                switch route {
                case .detail: TripContainerDetail(host: host, language: language, openManual: { entry in
                    guard host.manualEditor(for: entry) != nil, state.tripPath.last == .detail else {
                        host.retireManualPreview(entry); return
                    }
                    manualEntry = entry
                })
                case .proposal: TripContainerProposal(host: host, language: language, original: false)
                case .originalAction: TripContainerProposal(host: host, language: language, original: true)
                }
            }
        }
    }
}

private struct TripContainerDetail: View {
    let host: TripContainerHost
    let language: ShellLanguage
    let openManual: (ManualPreviewEntry) -> Void
    var body: some View {
        let action = host.captureAction()
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let presentation = host.presentation, host.canLoadDetail {
                    if host.showsSelectedDetail { TripDetailView(state: presentation, language: language.tripLanguage) }
                    else { Text(language.text("Read the selected trip to view its current version.", "读取选中行程以查看当前版本。")) }
                    Button(language.text("Edit a local draft", "编辑本地草稿")) {
                        guard let work = host.prepareManualEditor(context: action) else { return }
                        Task {
                            guard let entry = await host.performManualEditor(work), host.manualEditor(for: entry) != nil else { return }
                            openManual(entry)
                        }
                    }.disabled(action == nil || !host.canPrepareManualEditor)
                    if !host.hasManualResources {
                        Text(language.text("Local editing resources are unavailable.", "本地编辑资源尚不可用。"))
                    } else if host.manualEditorState == .loading {
                        ProgressView(language.text("Reading original formal Trip", "正在读取原正式行程"))
                    } else if host.manualEditorState == .missing || host.manualEditorState == .failed {
                        Text(language.text("The original formal source could not be read. No editor was created.", "无法读取原正式来源，未创建编辑器。"))
                    }
                    Button(language.text("Read current detail", "读取当前详情")) {
                        guard let work = host.prepareTrip(context: action) else { return }
                        Task { await host.perform(work) }
                    }.disabled(action == nil)
                } else { Text(language.text("Trip selection is unavailable.", "行程选择已不可用。")) }
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }.navigationTitle(language.text("Trip details", "行程详情"))
            .onDisappear { host.cancelManualSourceRead() }
    }
}

private struct TripContainerProposal: View {
    let host: TripContainerHost
    let language: ShellLanguage
    let original: Bool
    var body: some View {
        let action = host.captureAction()
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let presentation = host.presentation {
                    let selected = original ? presentation.selectedActionID != nil
                        : presentation.selectedActionID == nil && presentation.selectedProposalID == host.contextProposalID
                    if selected {
                        // Read-only canonical document/status/receipt. Its internal Task button is
                        // disabled; the host below prepares canonical opaque work before Task.
                        TripProposalCard(state: presentation, language: language.tripLanguage).disabled(true)
                    }
                    if original {
                        if let id = presentation.selectedActionID {
                            Text(language.text("Original action: ", "原动作：") + id).font(.caption).textSelection(.enabled)
                            if case .unknown = presentation.decision {
                                Button(language.text("Query this original action", "查询此原动作")) {
                                    guard let work = host.prepareReconciliation(context: action) else { return }
                                    Task { await host.perform(work) }
                                }.disabled(action == nil)
                            }
                        } else { Text(language.text("No original action is selected.", "未选择原动作。")) }
                    } else {
                        Button(language.text("Read current draft", "读取当前草稿")) {
                            guard let work = host.prepareProposal(context: action) else { return }
                            Task { await host.perform(work) }
                        }.disabled(action == nil || host.contextProposalID == nil)
                    }
                } else { Text(language.text("Trip connection is unavailable.", "行程连接已不可用。")) }
            }.frame(maxWidth: .infinity, alignment: .leading).padding()
        }.navigationTitle(language.text(original ? "Original action" : "Trip draft", original ? "原动作" : "行程草稿"))
    }
}

private struct TripContainerLoadLabel: View {
    let state: TripLoadState
    let language: ShellLanguage
    var body: some View {
        switch state {
        case .unavailable: Text(language.text("Not loaded or unavailable", "尚未读取或不可用"))
        case .idle, .loaded: EmptyView()
        case .loading: ProgressView(language.text("Loading…", "正在读取…"))
        case .missing: Text(language.text("No record returned", "未返回记录"))
        case .failed: Text(language.text("Could not read records.", "无法读取记录。"))
        case .unknown: Text(language.text("Result unknown. Query the original action.", "结果未知，请查询原动作。"))
        }
    }
}
#endif
