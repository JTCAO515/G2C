#if os(iOS)
import SwiftUI
import CJMemoryClient
import CJRunClient

private struct TypedMemorySurfaceLifecycle: ViewModifier {
    let host: TypedMemoryContainerHost
    @Binding var surface: TypedMemorySurface?
    var onBegin: () -> Void = {}
    func body(content: Content) -> some View {
        content.onAppear { onBegin();surface = host.enterSurface() }
            .onDisappear { host.leaveSurface(surface) }
    }
}
private struct TypedMemoryText: View {
    let text: String
    let id: String
    var body: some View {
        RunReadableText(text:text).frame(maxWidth:.infinity,alignment:.leading).accessibilityIdentifier(id)
    }
}
private func typedMemoryStatus(_ status: String,_ language: ShellLanguage) -> String {
    switch status {
    case "active":language.text("Active", "已启用")
    case "candidate":language.text("Candidate · unconfirmed", "候选 · 待确认")
    case "disabled":language.text("Disabled", "已停用")
    case "withdrawn":language.text("Stopped using · history retained", "已停止使用 · 历史保留")
    default:language.text("Unknown", "未知")
    }
}
private func typedMemoryScope(_ scope: TypedMemoryScope,_ language: ShellLanguage) -> String {
    switch scope {
    case .longTerm:language.text("Long-term memory", "长期记忆")
    case .legacyConversation(let id):language.text("Original conversation only: ", "仅原会话：") + id
    case .travel(let travel):language.text("Travel: ", "旅行：") + travel.id + " · " + language.text("version ", "版本 ") + String(travel.expectedVersion)
    }
}
private func typedMemoryKind(_ kind: String,_ language: ShellLanguage) -> String {
    switch kind {
    case "fact":MemoryGroup.facts.title(language)
    case "experience":MemoryGroup.experiences.title(language)
    case "preference":MemoryGroup.preferences.title(language)
    case "inference":language.text("Inference · unconfirmed", "推断 · 待确认")
    default:language.text("Unknown kind", "未知类型")
    }
}
private struct TypedMemoryButton: View {
    let title: String
    let id: String
    let enabled: Bool
    let action: () -> Void
    var body: some View {
        Button(action:action) {
            RunReadableText(text:title).frame(maxWidth:.infinity,minHeight:44,alignment:.leading).contentShape(Rectangle())
        }.buttonStyle(ShellReadableButtonStyle()).disabled(!enabled).accessibilityIdentifier(id)
    }
}

struct TypedMemoryItems: View {
    let host: TypedMemoryContainerHost
    @Bindable var shell: ShellState
    @State private var surface: TypedMemorySurface?
    private var language: ShellLanguage { shell.language }
    var body: some View {
        List {
            TypedMemoryButton(title:language.text("Read saved memories", "读取已保存记忆"),id:"memory2.items.read",enabled:surface != nil && !host.busy) {
                let captured = surface;Task { await host.loadItems(surface:captured) }
            }
            switch host.items {
            case .unconfigured:TypedMemoryText(text:language.text("Read memories to see their current status.", "请读取记忆以查看当前状态。"),id:"memory2.items.status")
            case .loading:ProgressView(language.text("Reading…", "正在读取…"))
            case .failed:TypedMemoryText(text:language.text("Memories could not be read. No empty or successful result is assumed.", "无法读取记忆，不能据此视为空列表或读取成功。"),id:"memory2.items.status")
            case .loaded(let rows):
                if rows.isEmpty { TypedMemoryText(text:language.text("No memories found.", "暂无记忆。"),id:"memory2.items.status") }
                ForEach(rows.indices,id:\.self) { index in
                    let read = rows[index],item = read.item.value
                    Button {
                        guard let route = host.detailRoute(for:read,surface:surface) else { return }
                        shell.memoryPath.append(route)
                    } label: {
                        VStack(alignment:.leading,spacing:6) {
                            TypedMemoryText(text:item.command.text,id:"memory2.item.text." + item.command.item_id)
                            TypedMemoryText(text:item.command.subject + " · " + item.command.slot + " · " + typedMemoryStatus(item.status.rawValue,language),id:"memory2.item.status." + item.command.item_id)
                            TypedMemoryText(text:typedMemoryScope(read.item.scope,language),id:"memory2.item.scope." + item.command.item_id)
                        }.frame(minHeight:44).contentShape(Rectangle())
                    }.buttonStyle(ShellReadableButtonStyle()).disabled(host.busy).accessibilityIdentifier("memory2.item." + item.command.item_id)
                }
            }
            if host.hasMore {
                TypedMemoryButton(title:language.text("Read next page", "读取下一页"),id:"memory2.items.next",enabled:!host.busy) {
                    let captured = surface;Task { await host.loadItems(surface:captured,more:true) }
                }
            }
        }.navigationTitle(language.text("Saved memories", "已保存记忆"))
            .modifier(TypedMemorySurfaceLifecycle(host:host,surface:$surface))
    }
}

struct TypedMemoryManual: View {
    let host: TypedMemoryContainerHost
    let language: ShellLanguage
    @State private var surface: TypedMemorySurface?
    @State private var optionID: UUID?
    @State private var text = ""
    @State private var occurredAt = ""
    @State private var review: TypedMemorySaveWork?
    @State private var reviewFailed = false
    private enum Input: Hashable { case text,time }
    @FocusState private var focusedInput: Input?
    var body: some View {
        Form {
            Section {
                if host.options.isEmpty {
                    TypedMemoryText(text:language.text("No subject or scope is available for saving.", "当前没有可保存的对象或范围。"),id:"memory2.manual.unavailable")
                }
                Picker(language.text("Subject and scope", "对象与范围"),selection:$optionID) {
                    Text(language.text("Choose explicitly", "请明确选择")).tag(UUID?.none)
                    ForEach(host.options) { option in Text(option.label).tag(Optional(option.id)) }
                }.accessibilityIdentifier("memory2.manual.option")
                if let travel = host.travelSelection {
                    NavigationLink { TravelSelectionView(model:travel,language:language) } label: {
                        RunReadableText(text:language.text("Choose travel context", "选择旅行上下文"))
                    }.accessibilityIdentifier("memory2.manual.travel")
                }
                TextField(language.text("Memory", "记忆内容"),text:$text,axis:.vertical)
                    .textFieldStyle(.roundedBorder).focused($focusedInput,equals:.text).frame(minHeight:44)
                    .contentShape(Rectangle()).onTapGesture { focusedInput = .text }.accessibilityIdentifier("memory2.manual.text")
                TextField(language.text("Approximate time; state if unknown", "大致时间；不清楚请明确说明"),text:$occurredAt)
                    .focused($focusedInput,equals:.time).submitLabel(.done).onSubmit { focusedInput = nil }
                    .textFieldStyle(.roundedBorder).frame(minHeight:44).contentShape(Rectangle())
                    .onTapGesture { focusedInput = .time }.accessibilityIdentifier("memory2.manual.time")
                TypedMemoryText(text:language.text("Only the subject, field and scope you review will be submitted. Inference remains an unconfirmed candidate.", "只提交你核对的对象、字段和范围；推断保持待确认候选。"),id:"memory2.manual.disclosure")
                TypedMemoryButton(title:language.text("Review before saving", "保存前核对"),id:"memory2.manual.review",enabled:surface != nil && !host.busy && optionID != nil && !text.isEmpty && !occurredAt.isEmpty) {
                    do {
                        focusedInput = nil
                        guard let optionID else { return }
                        review = try host.prepareSave(optionID:optionID,text:text,occurredAt:occurredAt,surface:surface);reviewFailed = false
                    } catch { review = nil;reviewFailed = true }
                }
                if reviewFailed { TypedMemoryText(text:language.text("The input, selected context or earlier originals could not be verified. Nothing new was submitted.", "无法核实输入、所选上下文或此前原操作；本次尚未新增提交。"),id:"memory2.manual.error") }
            }
            if let reviewed = review {
                let original = reviewed.original
                Section {
                    TypedMemoryText(text:original.text,id:"memory2.review.text")
                    TypedMemoryText(text:original.subject + " · " + original.slot + " · " + typedMemoryKind(original.kind.rawValue,language),id:"memory2.review.subject")
                    TypedMemoryText(text:original.occurredAt,id:"memory2.review.time")
                    TypedMemoryText(text:typedMemoryScope(original.travelContext.map(TypedMemoryScope.travel) ?? .longTerm,language),id:"memory2.review.scope")
                    TypedMemoryButton(title:language.text("Confirm save", "确认保存"),id:"memory2.manual.confirm",enabled:!host.busy) {
                        guard let captured = review else { return };review = nil
                        Task { await host.performSave(captured) }
                    }
                } header: { ShellSectionHeading(title:language.text("Review exact input", "核对本次原输入")) }
            }
            TypedMemorySaveOutcome(host:host,surface:surface,language:language)
            NavigationLink { TypedMemoryOriginals(host:host,language:language) } label: {
                RunReadableText(text:language.text("Previous operations", "此前的原操作"))
            }.accessibilityIdentifier("memory2.originals.open")
        }.navigationTitle(language.text("Add memory", "新增记忆"))
            .scrollDismissesKeyboard(.interactively)
            .toolbar { ToolbarItemGroup(placement:.keyboard) {
                Spacer();Button(language.text("Done", "完成")) { focusedInput = nil }
            } }
            .onChange(of:text) { _,_ in review = nil }.onChange(of:occurredAt) { _,_ in review = nil }.onChange(of:optionID) { _,_ in review = nil }
            .modifier(TypedMemorySurfaceLifecycle(host:host,surface:$surface,onBegin:{ focusedInput = nil;review = nil;reviewFailed = false }))
    }
}

struct TypedMemoryDetail: View {
    let host: TypedMemoryContainerHost
    let itemID: String
    let language: ShellLanguage
    @State private var surface: TypedMemorySurface?
    @State private var replacement = ""
    @State private var review: TypedMemoryManagementWork?
    @State private var reviewFailed = false
    @FocusState private var editFocused: Bool
    var body: some View {
        Form {
            TypedMemoryButton(title:language.text("Read current detail", "读取当前详情"),id:"memory2.detail.read",enabled:surface != nil && !host.busy) {
                review = nil;let captured = surface;Task { await host.loadDetail(itemID:itemID,surface:captured) }
            }
            switch host.detail {
            case .unconfigured:TypedMemoryText(text:language.text("Read the current record before reviewing a change.", "请先读取当前记录，再核对修改。"),id:"memory2.detail.state")
            case .loading:ProgressView(language.text("Reading…", "正在读取…"))
            case .failed:TypedMemoryText(text:language.text("Current detail unavailable.", "当前详情不可用。"),id:"memory2.detail.state")
            case .loaded(let value):
                if let read = value {
                    let item = read.item.value,c = item.command,status = item.status.rawValue
                    Section {
                        TypedMemoryText(text:c.text,id:"memory2.detail.text")
                        TypedMemoryText(text:typedMemoryStatus(status,language),id:"memory2.detail.status")
                        TypedMemoryText(text:c.subject + " · " + c.slot + " · " + typedMemoryKind(c.kind.rawValue,language),id:"memory2.detail.subject")
                        TypedMemoryText(text:typedMemoryScope(read.item.scope,language),id:"memory2.detail.scope")
                        TypedMemoryText(text:c.occurred_at,id:"memory2.detail.time")
                        TypedMemoryText(text:language.text("Source: ", "来源：") + c.source_id + " · " + String(c.source_version),id:"memory2.detail.source")
                        TypedMemoryText(text:language.text("Recorded: ", "记录时间：") + item.recorded_at.ISO8601Format(),id:"memory2.detail.recorded")
                        TypedMemoryText(text:language.text("Item version: ", "条目版本：") + String(item.version),id:"memory2.detail.version")
                    }
                    if status == "active" || status == "disabled" {
                        Section {
                            if case .legacyConversation = read.item.scope {
                                TypedMemoryText(text:language.text("The original conversation scope is retained. Editing that scope is unavailable in this entry.", "原会话范围保持；当前入口不支持编辑该范围。"),id:"memory2.detail.legacy")
                            } else {
                                TextField(language.text("Replacement text", "新的原文"),text:$replacement,axis:.vertical)
                                    .textFieldStyle(.roundedBorder).focused($editFocused).frame(minHeight:44).contentShape(Rectangle())
                                    .onTapGesture { editFocused = true }.accessibilityIdentifier("memory2.edit.text")
                                if let travel = host.travelSelection {
                                    NavigationLink { TravelSelectionView(model:travel,language:language) } label: {
                                        RunReadableText(text:language.text("Verify travel context", "核实旅行上下文"))
                                            .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).foregroundStyle(.primary)
                                    }
                                }
                                reviewButton(.edit,title:language.text("Review text change", "核对文字修改"),enabled:!replacement.isEmpty)
                            }
                            if status == "active" { reviewButton(.pause,title:language.text("Review pause", "核对暂停")) }
                            else { reviewButton(.resume,title:language.text("Review resume", "核对恢复")) }
                        }
                    }
                    if status != "withdrawn" { reviewButton(.stopUse,title:language.text("Review stop using", "核对停止使用")) }
                } else { TypedMemoryText(text:language.text("Memory not found.", "未找到该记忆。"),id:"memory2.detail.state") }
            }
            if reviewFailed { TypedMemoryText(text:language.text("A current record, matching travel or earlier original still needs verification. No new action was submitted.", "仍需核实当前记录、对应旅行或此前原操作；尚未新增提交。"),id:"memory2.manage.error") }
            if let reviewed = review {
                Section {
                    TypedMemoryText(text:operationLabel(reviewed.operation),id:"memory2.manage.review.operation")
                    TypedMemoryText(text:reviewed.originalItem.value.command.text,id:"memory2.manage.review.before")
                    if let text = reviewed.text { TypedMemoryText(text:text,id:"memory2.manage.review.after") }
                    TypedMemoryText(text:typedMemoryScope(reviewed.originalItem.scope,language),id:"memory2.manage.review.scope")
                    if let travel = reviewed.selectedTravel {
                        TypedMemoryText(text:language.text("Travel version for this action: ", "本次动作的旅行版本：") + travel.id + " · " + String(travel.expectedVersion),id:"memory2.manage.review.travel")
                    }
                    TypedMemoryText(text:language.text("Item/source versions: ", "条目/来源版本：") + String(reviewed.originalItem.value.version) + "/" + String(reviewed.originalItem.value.command.source_version),id:"memory2.manage.review.versions")
                    TypedMemoryText(text:language.text("Only this original action is submitted. Stopping use retains history and sources.", "仅提交本次原动作；停止使用保留历史及来源。"),id:"memory2.manage.review.disclosure")
                    TypedMemoryButton(title:language.text("Confirm this action", "确认本次操作"),id:"memory2.manage.confirm",enabled:!host.busy) {
                        guard let captured = review else { return };review = nil
                        Task { await host.performManagement(captured) }
                    }
                } header: { ShellSectionHeading(title:language.text("Review change", "核对修改")) }
            }
            TypedMemoryManagementOutcome(host:host,language:language)
            NavigationLink { TypedMemoryOriginals(host:host,language:language) } label: {
                RunReadableText(text:language.text("Previous operations", "此前的原操作"))
                    .frame(maxWidth:.infinity,minHeight:44,alignment:.leading).foregroundStyle(.primary)
            }
        }.navigationTitle(language.text("Memory", "记忆")).navigationBarTitleDisplayMode(.inline)
            .scrollDismissesKeyboard(.interactively)
            .toolbar { ToolbarItemGroup(placement:.keyboard) {
                Spacer();Button(language.text("Done", "完成")) { editFocused = false }
            } }
            .onChange(of:replacement) { _,_ in review = nil }
            .modifier(TypedMemorySurfaceLifecycle(host:host,surface:$surface,onBegin:{editFocused = false;review = nil;reviewFailed = false}))
    }
    private func operationLabel(_ operation: TypedMemoryOperation) -> String {
        switch operation {
        case .pause:language.text("Pause", "暂停")
        case .resume:language.text("Resume", "恢复")
        case .edit:language.text("Edit text", "编辑原文")
        case .stopUse:language.text("Stop using", "停止使用")
        }
    }
    private func reviewButton(_ operation: TypedMemoryOperation,title: String,enabled: Bool = true) -> some View {
        TypedMemoryButton(title:title,id:"memory2.manage.review." + operation.rawValue,enabled:enabled && !host.busy) {
            editFocused = false
            do { review = try host.prepareManagement(operation,text:operation == .edit ? replacement : nil,surface:surface);reviewFailed = false }
            catch { review = nil;reviewFailed = true }
        }
    }
}

private struct TypedMemorySaveOutcome: View {
    let host: TypedMemoryContainerHost
    let surface: TypedMemorySurface?
    let language: ShellLanguage
    private var query: (() -> Void)? {
        switch host.originalReference {
        case .save(let id):return { let captured = surface;Task { await host.querySave(operationID:id,surface:captured) } }
        case .legacySave(let id):return { let captured = surface;Task { await host.queryLegacySave(operationID:id,surface:captured) } }
        default:return nil
        }
    }
    var body: some View {
        MemorySaveStatusView(state:host.saveState,language:language == .english ? .english : .chinese,queryOriginal:host.busy ? nil : query,statusIdentifier:"memory2.save.status")
    }
}
private struct TypedMemoryManagementOutcome: View {
    let host: TypedMemoryContainerHost
    let language: ShellLanguage
    var body: some View {
        Group {
            switch host.managementState {
            case .ready:EmptyView()
            case .working:ProgressView(language.text("Checking the original action…", "正在核实原动作…"))
            case .unknown:message(language.text("Result unknown. Read the original action; do not resend.", "结果未知，请读取原动作，不要重发。"))
            case .notObserved:message(language.text("Original receipt not observed. This does not permit resubmission.", "尚未查到原回执，不代表可以重新提交。"))
            case .rejected:message(language.text("The original action was rejected. Read current detail before reviewing another action.", "原动作已被拒绝；请读取当前详情后再核对新动作。"))
            case .needsOriginalQuery:message(language.text("Query the earlier original first. No new action was submitted.", "请先查询此前原操作；本次没有新增提交。"))
            case .historical(let receipt):receiptText(receipt.action_id,version:receipt.version,status:receipt.status.rawValue)
            case .legacy(let result):
                switch result {
                case .historicalReceipt(let receipt):receiptText(receipt.action_id,version:receipt.version,status:receipt.status.rawValue)
                case .historicalStopUseReceipt(let receipt):receiptText(receipt.action_id,version:receipt.version,status:receipt.status.rawValue)
                case .notObserved:message(language.text("Earlier receipt not observed; keep the original action.", "尚未查到此前回执，请保留原动作。"))
                case .rejected:message(language.text("The earlier original was rejected; it is never resent here.", "此前原动作已被拒绝；此处不会重发。"))
                }
            }
        }.accessibilityIdentifier("memory2.manage.status")
    }
    private func message(_ value: String) -> some View { RunReadableText(text:value) }
    private func receiptText(_ id: String,version: Int,status: String) -> some View {
        message(language.text("Original receipt verified: ", "原回执已核实：") + id + " · " + String(version) + " · " + typedMemoryStatus(status,language)
            + language.text(". Read current detail to verify current use.", "。当前是否使用请重新读取详情。"))
    }
}

struct TypedMemoryOriginals: View {
    let host: TypedMemoryContainerHost
    let language: ShellLanguage
    @State private var surface: TypedMemorySurface?
    var body: some View {
        List {
            TypedMemoryButton(title:language.text("Read original journals", "读取原操作日志"),id:"memory2.originals.read",enabled:surface != nil && !host.busy) { host.loadOriginals(surface:surface) }
            Section {
                switch host.legacyRecoveryState {
                case .requiresQuery:RunReadableText(text:language.text("Earlier originals need verification before any new save.", "新增保存前，需要先核实此前原操作。"))
                case .unavailable:RunReadableText(text:language.text("Earlier journals cannot be verified; new writes remain unavailable.", "此前日志无法核实，新增提交保持不可用。"))
                case .reconciled:RunReadableText(text:language.text("Earlier journal outcomes are reconciled. New actions still require current authorization.", "此前日志结果已核实；新动作仍需当前授权。"))
                case .unconfigured:RunReadableText(text:language.text("Earlier-format recovery is not connected.", "此前格式的恢复入口未接入。"))
                }
            }
            Section {
                switch host.originals {
                case .loaded(let records):
                    if records.isEmpty { noOriginals }
                    ForEach(records.indices,id:\.self) { index in
                        let original = records[index]
                        VStack(alignment:.leading,spacing:6) {
                            RunReadableText(text:original.text)
                            queryButton(original.operationID,prefix:"memory2.original.query.") { let captured = surface;Task { await host.querySave(operationID:original.operationID,surface:captured) } }
                        }
                    }
                case .failed:journalError
                default:EmptyView()
                }
            } header: { ShellSectionHeading(title:language.text("Current save originals", "本版保存原操作")) }
            Section {
                if case .loaded(let records) = host.managementOriginals {
                    if records.isEmpty { noOriginals }
                    ForEach(records.indices,id:\.self) { index in
                        let original = records[index]
                        queryButton(original.actionID,prefix:"memory2.action.query.") { let captured = surface;Task { await host.queryManagement(actionID:original.actionID,surface:captured) } }
                    }
                } else if case .failed = host.managementOriginals { journalError }
            } header: { ShellSectionHeading(title:language.text("Current lifecycle originals", "本版管理原动作")) }
            Section {
                if case .loaded(let records) = host.legacyOriginals {
                    if records.isEmpty { noOriginals }
                    ForEach(records.indices,id:\.self) { index in
                        let original = records[index]
                        queryButton(original.operationID,prefix:"memory2.legacy.query.") { let captured = surface;Task { await host.queryLegacySave(operationID:original.operationID,surface:captured) } }
                    }
                } else if case .failed = host.legacyOriginals { journalError }
            } header: { ShellSectionHeading(title:language.text("Earlier save originals", "此前保存原操作")) }
            Section {
                if case .loaded(let records) = host.legacyManagementOriginals {
                    if records.isEmpty { noOriginals }
                    ForEach(records.indices,id:\.self) { index in
                        let original = records[index]
                        queryButton(original.actionID,prefix:"memory2.legacy.action.query.") { let captured = surface;Task { await host.queryLegacyManagement(actionID:original.actionID,surface:captured) } }
                    }
                } else if case .failed = host.legacyManagementOriginals { journalError }
            } header: { ShellSectionHeading(title:language.text("Earlier lifecycle originals", "此前管理原动作")) }
            if let original = host.originalReference {
                switch original {
                case .save(let id),.legacySave(let id):
                    RunReadableText(text:language.text("Original: ", "原操作：") + id)
                    TypedMemorySaveOutcome(host:host,surface:surface,language:language)
                case .management(let id),.legacyManagement(let id):
                    RunReadableText(text:language.text("Original action: ", "原动作：") + id)
                    TypedMemoryManagementOutcome(host:host,language:language)
                }
            }
        }.navigationTitle(language.text("Previous operations", "此前的原操作"))
            .modifier(TypedMemorySurfaceLifecycle(host:host,surface:$surface))
    }
    private var journalError: some View { RunReadableText(text:language.text("This journal could not be read. Other originals can still be queried.", "无法读取这组日志，仍可查询其他原操作。")) }
    private var noOriginals: some View { RunReadableText(text:language.text("No original operations found in this journal.", "这组日志中未发现原操作。")) }
    private func queryButton(_ id: String,prefix: String,action: @escaping () -> Void) -> some View {
        TypedMemoryButton(title:language.text("Query original: ", "查询原操作：") + id,id:prefix + id,enabled:surface != nil && !host.busy,action:action)
    }
}
#endif
