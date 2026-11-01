#if os(iOS)
import SwiftUI
import UIKit
import CJTripClient
import CJRunClient

struct StructuredTripHome: View {
    let host: StructuredTripHost
    let legacy: TripContainerHost
    @Bindable var state: ShellState
    @State private var issue: String?
    @State private var task: Task<Void,Never>?
    @State private var panel: Panel = .record
    private enum BrowsePanel: Identifiable {
        case records(UUID), timeline(UUID, TripTimelineHost)
        var id: UUID { switch self { case .records(let id): id; case .timeline(let id, _): id } }
    }
    @State private var browsePanel: BrowsePanel?
    private enum Panel { case record, editor, diff }
    private var language: ShellLanguage { state.language }
    private var edit: ManualTripDisplay? { host.editor?.display() }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:18) {
                    RunReadableText(text:language.text("Local synthetic test data", "本地合成测试数据"),style:.caption).accessibilityIdentifier("trip.manual.synthetic")
                    RunReadableText(text:language.text("Only your explicit selected edits are submitted. Saving confirms that exact server diff once; it does not update Memory or requirements.","只提交你明确选中的修改。保存仅确认这份服务器差异，不修改记忆或需求。"))
                    if let display=host.display() {
                        RunReadableText(text:loadMessage(display.state)).accessibilityIdentifier("trip.structured.state")
                        button("trip.structured.refresh",language.text("Read formal trips","读取正式行程"),disabled:display.busy) { run { try host.page() } }
                        ForEach(display.trips,id:\.tripID) { row in
                            button("trip.structured.item."+row.tripID,row.title+" · "+String(row.version),disabled:display.busy) {
                                panel = .record;run { try host.detail(id:row.tripID) }
                            }
                        }
                        if display.hasNext {
                            button("trip.structured.next",language.text("Read next page","读取下一页"),disabled:display.busy) { run { try host.page(more:true) } }
                        }
                        if let record=display.selected {
                            Divider()
                            RunReadableText(text:record.tripID+" · "+language.text("Read version ","读取版本 ")+String(record.version)).accessibilityIdentifier("trip.manual.basis")
                            button("trip.manual.current",language.text("Read current version (keep input)","读取当前版本（保留输入）"),disabled:display.busy) { run { try host.currentRecord() } }
                            if let observed=display.currentObservation {
                                RunReadableText(text:language.text("Current observation: version ","当前观测：版本 ")+String(observed.version)+language.text(". The editor's basis has not changed.","；编辑器基准没有改变。"))
                                    .accessibilityIdentifier("trip.manual.current.version")
                            }
                            button("trip.manual.replaceBasis",language.text("Read and explicitly replace the local basis/input","读取并明确替换本地基准和输入"),disabled:display.busy) {
                                panel = .record;run { try host.detail(id:record.tripID) }
                            }
                            DisclosureGroup(isExpanded:Binding(get:{panel == .record},set:{ if $0 { panel = .record } })) {
                                StructuredTripDocumentView(document:record.document,language:language,prefix:"trip.manual.record")
                            } label: { RunReadableText(text:language.text("Read record","已读记录")).accessibilityIdentifier("trip.manual.record.open") }
                            if record.document.version == .needsBound {
                                RunReadableText(text:needsLabel()).accessibilityIdentifier("trip.manual.needs.status")
                                button("trip.manual.needs.read",language.text("Read explicitly selected requirements","读取明确选定的需求"),disabled:display.busy) { run { try host.needs() } }
                                RunReadableText(text:language.text("The server verifies the Trip's original requirements; this selection is not source permission.","服务端会核对此行程的原需求；这里的选择不构成来源许可。"),style:.caption)
                            }
                            button("trip.manual.edit.open",language.text("Start explicit local edits","开始明确的本地编辑"),disabled:display.busy) {
                                act { try host.openEditor();panel = .editor }
                            }
                        }
                        if let edit {
                            RunReadableText(text:editorMessage(edit)).accessibilityIdentifier("trip.manual.editor.state")
                            if let refusal=edit.refusal {
                                RunReadableText(text:(refusal.status == 409
                                    ? language.text("Version conflict. Input retained; read the current version and explicitly choose a new basis. ","版本冲突。输入已保留；请读取当前版本并明确选择新基准。")
                                    : language.text("Original request refused; input retained. ","原请求被拒；输入已保留。"))+String(refusal.status)+" · "+refusal.code)
                                    .accessibilityIdentifier("trip.manual.refusal")
                            }
                            DisclosureGroup(isExpanded:Binding(get:{panel == .editor},set:{ if $0 { panel = .editor } })) {
                                ManualTripForm(draft:edit.draft,language:language,change:{ value in act { try host.updateDraft(value) } })
                            } label: { RunReadableText(text:language.text("Unsaved input","未保存输入")).accessibilityIdentifier("trip.manual.input.open") }
                            button("trip.manual.prepare",language.text("Prepare selected changes","准备选定修改"),disabled:display.busy || !edit.canPrepare) { run { try host.prepare(save:false) } }
                            if let prepared=edit.preparation {
                                DisclosureGroup(isExpanded:Binding(get:{panel == .diff},set:{ if $0 { panel = .diff } })) {
                                    RunReadableText(text:language.text("Before","修改前"),style:.headline)
                                    StructuredTripDocumentView(document:prepared.before,language:language,prefix:"trip.manual.before")
                                    RunReadableText(text:language.text("After · uncommitted","修改后 · 尚未提交"),style:.headline)
                                    StructuredTripDocumentView(document:prepared.after,language:language,prefix:"trip.manual.after")
                                    if let report=prepared.feasibility {
                                        RunReadableText(text:language.text("Overall feasibility remains ","整体可行性仍为 ")+report.status.rawValue).accessibilityIdentifier("trip.manual.feasibility")
                                        ForEach(report.checks.indices,id:\.self) { index in
                                            RunReadableText(text:language == .english ? report.checks[index].english : report.checks[index].chinese)
                                        }
                                    } else {
                                        RunReadableText(text:language.text("No overall feasibility report was returned. Save rechecks the original source, scope and version.","接口未返回整体可行性报告。保存时仍会复核原来源、选定范围和版本。"))
                                    }
                                    DisclosureGroup(language.text("Original server diff","服务器原始差异")) {
                                        RunSelectableText(text:String(decoding:prepared.originalDiffUTF8,as:UTF8.self)).accessibilityIdentifier("trip.manual.diff.raw")
                                    }
                                } label: { RunReadableText(text:language.text("Review exact server changes","核对服务器准确改动")).accessibilityIdentifier("trip.manual.diff.open") }
                            }
                            button("trip.manual.save",language.text("Save this reviewed diff","保存这份已核对的差异"),disabled:display.busy || !edit.canSave) { run { try host.prepare(save:true) } }
                            if let receipt=edit.receipt {
                                RunSelectableText(text:language.text("Original receipt: ","原动作回执：")+receipt.actionID+" · "+String(receipt.committedVersion))
                                    .accessibilityIdentifier("trip.manual.receipt")
                                RunReadableText(text:language.text("This proves that original commit, not the current Trip version.","这只证明该原动作的提交，不代表当前行程版本。"),style:.caption)
                            }
                        }
                        if display.busy {
                            ProgressView()
                            button("trip.manual.stop",language.text("Stop waiting; reconcile the original","停止等待，随后核对原动作")) { host.stopWaiting();task?.cancel() }
                        }
                        Divider()
                        button("trip.manual.originals.read",language.text("Read retained original actions","读取保留的原动作"),disabled:display.busy) { act { try host.loadOriginals() } }
                        ForEach(display.originals,id:\.storageID) { original in
                            DisclosureGroup {
                                RunSelectableText(text:original.tripID+" · "+String(original.originalVersion)+"\n"+String(decoding:original.originalUTF8,as:UTF8.self)).accessibilityIdentifier("trip.manual.original.input."+original.storageID)
                                button("trip.manual.original.query."+original.storageID,language.text("Query this original only","只查询此原动作"),disabled:display.busy) { run { try host.query(storageID:original.storageID) } }
                            } label: {
                                RunReadableText(text:original.originalID).accessibilityIdentifier("trip.manual.original.open."+original.storageID)
                            }
                        }
                        if let result=display.originalOutcome {
                            RunReadableText(text:historyMessage(result)).accessibilityIdentifier("trip.manual.original.result")
                        }
                    } else { RunReadableText(text:language.text("Trip context is unavailable. Read again in the current account.","行程上下文不可用，请在当前账号下重新读取。")) }
                    if let issue { RunReadableText(text:issue).accessibilityIdentifier("trip.manual.issue") }
                    button("trip.manual.browse", language.text("Timelines, browsing and original actions","时间线、浏览与原动作")) { browsePanel = .records(UUID()) }
                }.frame(maxWidth:.infinity,alignment:.leading).padding()
            }.accessibilityIdentifier("trip.manual.content").scrollDismissesKeyboard(.interactively)
                .navigationTitle(language.text("Edit trip","编辑行程")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement:.topBarLeading) {
                    Button { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder),to:nil,from:nil,for:nil) }
                    label: { Image(systemName:"keyboard.chevron.compact.down").frame(minWidth:44,minHeight:44) }
                        .accessibilityLabel(language.text("Hide keyboard","收起键盘")).accessibilityIdentifier("trip.manual.keyboard.done")
                } }
                .onChange(of:edit?.state) { _,value in if value == .prepared { panel = .diff } }
        }
        .sheet(item: $browsePanel) { panel in
            switch panel {
            case .records:
                TripShell(state: state, host: legacy, onClose: { browsePanel = nil }, openTimeline: {
                    act {
                        guard let reader = legacy.makeTimelineReader() else { throw TripFailure.staleBinding }
                        browsePanel = .timeline(UUID(), reader)
                    }
                })
            case .timeline(_, let reader):
                let messages = state.messageHost
                TripTimelineView(host: reader, language: language, onDiscuss: messages?.supportsTripMessages == true ? { entry in
                    guard state.messageHost === messages, messages?.selectTripDiscussion(entry) == true else { return false }
                    browsePanel = nil; state.selectedTab = .assistant; return true
                } : nil)
            }
        }
        .onChange(of: state.selectedTab) { _, tab in if tab != .trips { browsePanel = nil } }
        .onChange(of: state.generation) { _, _ in browsePanel = nil }
    }
    private func button(_ id: String,_ title: String,disabled: Bool = false,action:@escaping ()->Void) -> some View {
        Button(action:action) { RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle()) }
            .buttonStyle(ShellReadableButtonStyle()).disabled(disabled).accessibilityIdentifier(id)
    }
    private func run(_ make:()throws->StructuredTripHostWork) {
        act { let work=try make();task=Task { await host.perform(work) } }
    }
    private func act(_ body:()throws->Void) {
        do { try body();issue=nil }
        catch TripFailure.pendingRequiresQuery { issue=language.text("Reconcile retained original actions before another write.","再次写入前，请先核对保留的原动作。") }
        catch { issue=language.text("Cannot complete this choice. Keep the input and read the current account, record and requirements.","无法完成此选择。请保留输入，读取当前账号、记录与需求后再操作。") }
    }
    private func needsLabel() -> String {
        do {
            if let ref=try host.selectedNeeds() { return language.text("Selected requirements: ","选定需求：")+ref.id+" · "+String(ref.expectedVersion) }
            return language.text("No selected requirements snapshot has been read.","尚未读到选定需求的快照。")
        } catch { return language.text("Requirements context is unavailable.","需求上下文不可用。") }
    }
    private func loadMessage(_ value: StructuredTripLoadState) -> String {
        switch value {
        case .idle: language.text("No formal records read yet.","尚未读取正式记录。")
        case .loading: language.text("Reading the captured selection…","正在读取已捕获的选择…")
        case .loaded: language.text("Formal record read.","已读取正式记录。")
        case .missing: language.text("No visible structured record for this selection.","此选择没有可见的结构化记录。")
        case .unavailable: language.text("Operation unavailable; keep input and reconcile the original.","操作不可用；请保留输入并核对原动作。")
        }
    }
    private func editorMessage(_ value: ManualTripDisplay) -> String {
        switch value.state {
        case .editing: language.text("Unsaved local input · original basis kept","未保存的本地输入 · 保留原基准")
        case .preparing: language.text("Preparing this original diff…","正在准备此原差异…")
        case .prepared: language.text("Exact diff prepared · not saved","准确差异已准备 · 尚未保存")
        case .saving: language.text("Submitting this original save…","正在提交此原保存动作…")
        case .saved: language.text("Original receipt verified · historical commit","原动作回执已核对 · 历史提交")
        case .rejected: language.text("Original request refused; retain input and query it.","原请求被拒；保留输入并查询原动作。")
        case .unknown: language.text("Result unknown. Query the original; never automatically resend.","结果未知。请查询原动作，不自动重发。")
        }
    }
    private func historyMessage(_ value: ManualTripOutcome) -> String {
        switch value {
        case .prepared(let p): language.text("Original preparation verified: ","原准备记录已核对：")+p.requestID+" · "+p.status.rawValue
        case .saved(let r): language.text("Original receipt verified: ","原回执已核对：")+r.actionID+" · "+String(r.committedVersion)
        case .rejected(_,let code): language.text("Original refusal verified: ","原拒绝已核对：")+code
        case .notObserved: language.text("Original not observed; outcome remains unknown. No new write is permitted.","未观察到原动作，结果仍未知；不允许新写入。")
        }
    }
}

struct StructuredTripDocumentView: View {
    let document: StructuredTripDocument
    let language: ShellLanguage
    let prefix: String
    var body: some View {
        VStack(alignment:.leading,spacing:12) {
            RunSelectableText(text:document.title).accessibilityIdentifier(prefix+".title")
            RunReadableText(text:language.text("Bookings, source labels and time declarations are not externally verified.","预订、来源标签和时间声明未由外部服务核实。"),style:.caption)
            ForEach(document.items) { item in
                VStack(alignment:.leading,spacing:8) {
                    RunSelectableText(text:item.id+"\n"+item.text).accessibilityIdentifier(prefix+".item."+item.id)
                    RunSelectableText(text:language.text("Protection: ","保护：")+lock(item.fixed)+"\n"+language.text("Source: ","来源：")+item.sourceCategory.rawValue+" · "+item.verification.rawValue)
                        .accessibilityIdentifier(prefix+".fixed."+item.id)
                    RunSelectableText(text:language.text("Start: ","开始：")+event(item.start)+"\n"+language.text("End: ","结束：")+event(item.end))
                        .accessibilityIdentifier(prefix+".schedule."+item.id)
                }.padding(.vertical,8)
            }
        }
    }
    private func event(_ e: StructuredTripEvent) -> String {
        [e.date,e.time,e.timezone,e.utcOffset].map { tripObservationText($0,language:language) }.joined(separator:" · ")
    }
    private func lock(_ value: TripObservation<Bool>) -> String {
        switch value {
        case .known(true): language.text("Explicitly fixed","明确固定")
        case .known(false): language.text("Explicitly unlocked","明确未固定")
        case .missing: language.text("Explicitly missing","明确缺失")
        case .unknown: language.text("Unknown; content stays protected","未知；内容保持保护")
        case .uncertain(let note): language.text("Uncertain: ","不确定：")+note
        }
    }
}
func tripObservationText(_ value: TripObservation<String>,language: ShellLanguage) -> String {
    switch value {
    case .known(let text): text
    case .missing: language.text("Explicitly missing","明确缺失")
    case .unknown: language.text("Unknown","未知")
    case .uncertain(let note): language.text("Uncertain: ","不确定：")+note
    }
}
#endif
