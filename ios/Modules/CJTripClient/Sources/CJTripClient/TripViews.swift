import SwiftUI
import CJAPI

public enum TripLanguage: Sendable { case english, simplifiedChinese
    func text(_ english: String, _ chinese: String) -> String { self == .english ? english : chinese }
}

public struct TripProposalCard: View {
    public let state: TripPresentation
    public let language: TripLanguage
    public init(state: TripPresentation, language: TripLanguage) { self.state = state; self.language = language }
    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TripLoadLabel(state: state.proposalState, language: language)
            if let proposal = state.proposal {
                TripDocumentView(document: proposal.document, language: language)
                Text(status(proposal.status)).font(.headline)
                if proposal.status == .pending && Double(proposal.expires_at) <= Date().timeIntervalSince1970 {
                    Text(language.text("The displayed deadline has elapsed. Refresh to check server status.", "显示的有效期已过，请刷新核对服务端状态。"))
                }
                Text(language.text("Expected version: \(proposal.expected_version) · Basis: \(proposal.basis_version)",
                                   "预期版本：\(proposal.expected_version) · 依据：\(proposal.basis_version)"))
                Text(language.text("Expires: ", "有效期至：") + Date(timeIntervalSince1970: Double(proposal.expires_at)).formatted())
                DisclosureGroup(language.text("Candidate details", "候选详情")) {
                    Text(proposal.proposal_id).textSelection(.enabled)
                    Text(proposal.candidate_hash).font(.caption.monospaced()).textSelection(.enabled)
                    if let data = Data(base64Encoded: proposal.content_utf8_base64), let original = String(data: data, encoding: .utf8) {
                        Text(original).font(.caption.monospaced()).textSelection(.enabled)
                    }
                }
                decision
                HStack {
                    Button(language.text("Accept", "接受")) { start(.accept) }
                    Button(language.text("Reject draft", "拒绝草稿")) { start(.reject) }
                }.disabled(!canStart)
                if !state.acceptsUserActions {
                    Text(language.text("Confirmation is unavailable. Viewing this draft does not submit a decision.", "确认功能尚不可用。查看草稿不会提交接受或拒绝。"))
                        .font(.footnote)
                } else {
                    Text(language.text("Choosing only prepares the action. Nothing is saved until you confirm it.", "选择只会准备动作，确认之前不会保存任何内容。"))
                        .font(.footnote)
                }
                Text(language.text("Rejecting a draft and stopping generation are separate actions.", "拒绝已生成草稿与停止生成是不同操作。"))
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }.accessibilityElement(children: .contain)
    }
    private var canStart: Bool {
        guard state.acceptsUserActions, state.proposal?.status == .pending else { return false }
        switch state.decision {
        case .unavailable, .prepareFailed, .expiredUncommitted: return true
        default: return false
        }
    }
    private func start(_ kind: TripActionKind) {
        if let work = state.prepareDecision(kind) { Task { await state.perform(work) } }
    }
    @ViewBuilder private var decision: some View {
        switch state.decision {
        case .unavailable: EmptyView()
        case .preparing: ProgressView(language.text("Preparing the action for your confirmation", "正在准备待确认的动作"))
        case .prepareFailed:
            Text(language.text("The action could not be prepared. Nothing was saved; review the draft and try again.", "未能准备该动作，未保存任何内容；请重新查看草稿后再试。"))
        case .expiredUncommitted:
            Text(language.text("That confirmation expired and was not saved. Review the draft again before deciding.", "该确认已过期且未保存。请重新查看草稿后再决定。"))
        case .awaitingConfirmation(let prepared):
            VStack(alignment: .leading, spacing: 8) {
                Text(prepared.kind == .accept ? language.text("Confirm: accept this draft as your trip", "确认：接受此草稿为你的行程")
                                              : language.text("Confirm: reject this draft", "确认：拒绝此草稿")).font(.headline)
                Text(prepared.proposal.document.title)
                Text(language.text("Confirm before: ", "请在此时间前确认：") + Date(timeIntervalSince1970: Double(prepared.expiresAt)).formatted())
                    .font(.footnote)
                HStack {
                    Button(language.text("Confirm", "确认")) {
                        if let work = state.prepareConfirmation() { Task { await state.perform(work) } }
                    }.buttonStyle(.borderedProminent)
                    Button(language.text("Cancel", "取消")) { state.cancelConfirmation() }
                }
            }.accessibilityElement(children: .contain)
        case .submitting: ProgressView(language.text("Submitting original action", "正在提交原动作"))
        case .unknown:
            Text(language.text("Result unknown. Check the original action; do not submit again.", "结果未知。请查询原动作，不要再次提交。"))
            Button(language.text("Check original action", "查询原动作")) { if let work = state.prepareReconciliation() { Task { await state.perform(work) } } }
        case .reconciling: ProgressView(language.text("Checking original action", "正在查询原动作"))
        case .confirmed(let receipt):
            Text(receipt.kind == .accept ? language.text("Accepted", "已接受") : language.text("Rejected", "已拒绝"))
            if case .case1(let version) = receipt.committed_version {
                Text(language.text("Original receipt version: \(version). This is not the latest trip version.", "原回执版本：\(version)。这不是当前行程最新版本。"))
            }
        }
    }
    private func status(_ status: Components.Schemas.SourceTripProposalSnapshot.statusPayload) -> String {
        switch status {
        case .pending: language.text("Pending decision; eligibility is checked by the server", "待决定；是否有效由服务端核验")
        case .accepted: language.text("Accepted candidate", "候选已接受")
        case .rejected: language.text("Rejected candidate", "候选已拒绝")
        case .expired: language.text("Expired candidate", "候选已过期")
        case .superseded: language.text("Replaced by a newer candidate", "已被新候选取代")
        }
    }
}

public struct TripListView: View {
    public let state: TripPresentation
    public let language: TripLanguage
    public let pageSize: Int
    public init(state: TripPresentation, language: TripLanguage, pageSize: Int) {
        self.state = state; self.language = language; self.pageSize = pageSize
    }
    public var body: some View {
        List {
            Section {
                TripLoadLabel(state: state.listState, language: language)
                if state.listState == .loaded && state.trips.isEmpty {
                    Text(language.text("No trips returned", "暂无行程"))
                }
                ForEach(state.trips, id: \.trip_id) { trip in
                    Button { if let work = state.prepareTrip(id: trip.trip_id) { Task { await state.perform(work) } } } label: {
                        VStack(alignment: .leading) {
                            Text(trip.document.title)
                            Text(language.text("Current version \(trip.version)", "当前版本 \(trip.version)")).font(.caption)
                        }
                    }
                }
                if state.next != nil {
                    Button(language.text("Load next page", "加载下一页")) { if let work = state.prepareTrips(limit: pageSize, more: true) { Task { await state.perform(work) } } }
                        .disabled(state.listState == .loading)
                }
                Button(language.text("Refresh trips", "刷新行程")) { if let work = state.prepareTrips(limit: pageSize) { Task { await state.perform(work) } } }
                Text(language.text("Live pages may change while browsing.", "浏览期间，分页内容可能更新。"))
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section(language.text("Original actions", "原动作")) {
                TripLoadLabel(state: state.pendingState, language: language)
                ForEach(state.pendingActions, id: \.actionID) { action in
                    Button(action.proposal.document.title) { state.selectPending(actionID: action.actionID) }
                }
                Button(language.text("Load pending actions", "读取待对账动作")) { state.loadPending() }
            }
        }
    }
}

public struct TripDetailView: View {
    public let state: TripPresentation
    public let language: TripLanguage
    public init(state: TripPresentation, language: TripLanguage) { self.state = state; self.language = language }
    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TripLoadLabel(state: state.detailState, language: language)
            if let trip = state.trip {
                Text(language.text("Current formal version \(trip.version)", "当前正式版本 \(trip.version)")).font(.headline)
                    .accessibilityIdentifier("trip.detail.version")
                Text(trip.trip_id).font(.caption.monospaced()).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("trip.detail.id")
                TripDocumentView(document: trip.document, language: language)
            }
        }
    }
}

private struct TripDocumentView: View {
    let document: Components.Schemas.SourceTripContent
    let language: TripLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(document.title).font(.title2)
            ForEach(document.displayItems, id: \.id) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.categoryLabel(language)).font(.caption).fontWeight(.semibold)
                    Text(item.text).textSelection(.enabled)
                    if item.category == .estimated {
                        Text(language.text("Estimate at query time; not a future guarantee.", "查询时的估算，不保证未来实际情况。"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    ForEach(document.sources.filter { item.sourceRefs.contains($0.id) }, id: \.id) { source in
                        if source.evidence_level == .synthetic {
                            Text(language.text("Synthetic example — not a live query", "合成样例，并非实时查询"))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Label {
                        TripVerificationText(text: item.verification == .pending ? language.text("Pending verification", "待核实") : language.text("Evidence recorded", "已有核实依据"))
                    } icon: {
                        Image(systemName: item.verification == .pending ? "questionmark.circle" : "doc.text.magnifyingglass")
                    }.font(.caption).foregroundStyle(.primary)
                    ForEach(Array(item.evidence.enumerated()), id: \.offset) { _, evidence in Text(evidence).font(.caption).textSelection(.enabled) }
                }
            }
            if case .SourceDocumentV1(let sourceDocument) = document {
                Text(sourceDocument.decisions.travel_dates == .undecided
                     ? language.text("Travel dates not decided", "出行日期待决定")
                     : language.text("Travel dates need confirmation", "请确认出行日期"))
                    .font(.footnote)
            }
            Text(language.text("Accepting a trip does not verify pending facts.", "接受行程不代表待核实事实已获核实。"))
                .font(.footnote).foregroundStyle(.primary)
        }
    }
}
// Local rendering adapter follows MemoryRowText's audited native measurement.
// Avoid a new Trip -> Run dependency for the largest dynamic type size.
#if os(iOS)
import UIKit
private struct TripVerificationText: UIViewRepresentable {
    let text: String
    func makeUIView(context: Context) -> UILabel {
        let label = UILabel()
        label.numberOfLines = 0
        label.lineBreakMode = .byWordWrapping
        label.textColor = .label
        label.adjustsFontForContentSizeCategory = true
        label.setContentCompressionResistancePriority(.required, for: .vertical)
        return label
    }
    func updateUIView(_ label: UILabel, context: Context) {
        label.text = text
        label.font = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: label.traitCollection)
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    static func dismantleUIView(_ uiView: UILabel, coordinator: ()) { uiView.text = nil }
}
#else
private struct TripVerificationText: View {
    let text: String
    var body: some View { Text(text).font(.caption).foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true) }
}
#endif
private struct TripLoadLabel: View {
    let state: TripLoadState
    let language: TripLanguage
    var body: some View {
        switch state {
        case .unavailable: Text(language.text("Not connected", "尚未连接"))
        case .idle, .loaded: EmptyView()
        case .loading: ProgressView(language.text("Loading", "正在读取"))
        case .missing: Text(language.text("No record returned", "未返回记录"))
        case .failed: Text(language.text("Could not load. Retry the read when available.", "读取失败，可在恢复后重新读取。"))
        case .unknown: Text(language.text("Result unknown", "结果未知"))
        }
    }
}

#Preview("Unavailable / English") { TripProposalCard(state: TripPresentation(client: nil), language: .english).padding() }
#Preview("未连接 / 中文") { TripListView(state: TripPresentation(client: nil), language: .simplifiedChinese, pageSize: 20) }

#Preview("Synthetic pending content / 合成内容") {
    TripDocumentView(document: .init(title: "Synthetic example / 合成样例", items: [
        .init(id: "preview-item", text: "Pending travel detail / 待核实行程内容", verification: .pending, evidence: [])
    ]), language: .simplifiedChinese).padding()
}
