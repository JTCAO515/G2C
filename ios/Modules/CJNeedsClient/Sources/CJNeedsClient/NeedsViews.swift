import SwiftUI
import CJAPI

/// Embeddable content, without navigation or session ownership. CJ006 supplies the trusted model.
public struct NeedsClientView: View {
    @Bindable private var model: NeedsPresentation
    private let language: NeedsLanguage
    @State private var historyVersion = ""
    public init(model: NeedsPresentation, language: NeedsLanguage) { self.model = model; self.language = language }
    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text(language.text("本次需求与固定事项", "Journey needs & fixed items")).font(.title2)
                Text(language.text("系统提取与对话来源绑定尚未接入。这里只呈现用户明确提供的本次条件，不自动写入长期记忆或正式行程。", "System extraction and conversation source binding are not connected. These are explicit user-provided journey details; they are not automatically saved to long-term memory or a formal trip."))
                    .font(.footnote)
                Text(model.state.message(language)).accessibilityIdentifier("needs.state")
                if let snapshot = model.snapshot { NeedsDetailsView(fields: snapshot.fields, version: snapshot.version, language: language) }
                if let revision = model.revision {
                    NeedsDetailsView(fields: revision.fields, version: revision.version, language: language)
                    if let bytes = Data(base64Encoded: revision.original_input_utf8_base64),
                       let command = try? JSONDecoder().decode(NeedsSchema.NeedsCommand.self, from: bytes) {
                        LabeledContent(language.text("本次修订的原始说明", "Original statement for this revision"), value: command.source.text)
                        Text(language.text("这段说明属于该次修订，不代表所有保留字段的来源。", "This statement belongs to this revision, not every retained field."))
                            .font(.footnote)
                    }
                }
                if let id = model.selectedNeedsID {
                    Button(language.text("读取最新版本（保留编辑）", "Read latest (keep edits)")) {
                        if let work = model.prepareDetail(id: id) { Task { await model.perform(work) } }
                    }
                    HStack {
                        TextField(language.text("历史版本号", "Historical version"), text: $historyVersion)
                            .textFieldStyle(.roundedBorder)
                        Button(language.text("读取历史版本", "Read revision")) {
                            if let version = Int(historyVersion), version > 0,
                               let work = model.prepareRevision(id: id, version: version) { Task { await model.perform(work) } }
                        }.disabled(Int(historyVersion).map { $0 > 0 } != true)
                    }
                }
                if let draft = model.draft {
                    NeedsEditorView(draft: Binding(get: { model.draft ?? draft }, set: { if model.draft?.editorID == draft.editorID { model.draft = $0 } }), language: language)
                    Button(language.text("保存明确修改", "Save explicit changes")) {
                        if let work = model.prepareSave(actionID: UUID().uuidString) { Task { await model.perform(work) } }
                    }.disabled(!model.canSave || model.state == .loading || model.selectedActionID != nil)
                    Text(language.text("账号、资源与收集策略尚未配置，真实保存已关闭；编辑仅留在当前界面。", "Account, resources and collection policy are not configured. Live saving is disabled; edits remain in this screen."))
                        .font(.footnote).accessibilityIdentifier("needs.writeUnavailable")
                }
                Button(language.text("读取待核对动作", "Read pending actions")) { model.loadPending() }
                Text(model.pendingState.message(language)).font(.footnote)
                ForEach(model.pendingActions, id: \.actionID) { action in
                    VStack(alignment: .leading) {
                        Text(action.command.source.text)
                        Text(language.text("原版本：", "Original version: ") + String(action.command.expected_version)).font(.caption)
                        Button(language.text("核对这个原动作", "Reconcile this original action")) {
                            if let work = model.prepareQuery(actionID: action.actionID) { Task { await model.perform(work) } }
                        }
                    }
                }
            }.padding()
        }
    }
}

public struct NeedsEditorView: View {
    @Binding private var draft: NeedsDraft
    private let language: NeedsLanguage
    public init(draft: Binding<NeedsDraft>, language: NeedsLanguage) { _draft = draft; self.language = language }
    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(language.text("纠正本次条件", "Correct journey details")).font(.headline)
            Text(language.text("只提交主动修改的字段；日期未定也可以保留。金额原样保存，不换算或平均。", "Only explicitly edited fields are included. Dates may remain undecided. Amounts are preserved without conversion or division."))
                .font(.footnote)
            Text(language.text("编辑基于版本：", "Editing version: ") + String(draft.expectedVersion))
            TextField(language.text("说明你的明确输入或修改", "Describe your explicit input or correction"), text: $draft.sourceText, axis: .vertical)
                .lineLimit(1...4).autocorrectionDisabled()
                .textFieldStyle(.roundedBorder).accessibilityIdentifier("needs.editor.statement")
            ForEach(NeedsField.allCases, id: \.self) { field in
                DisclosureGroup {
                    ObservationEditor(input: Binding(get: { draft.observations[field] ?? .init() }, set: { draft.set(field, $0) }),
                                      language: language, id: "needs.editor." + field.rawValue, isList: field == .includes, choices: field == .basis ? [("total", language.text("总计", "Total")), ("per_person", language.text("每人", "Per person"))] : [])
                    Text(draft.changedFields.contains(field) ? language.text("将包含此修改", "This change is included") : language.text("不修改此字段", "Leave this field unchanged"))
                        .font(.caption)
                } label: { NeedsFormLabel(text: field.label(language)).accessibilityIdentifier("needs.editor." + field.rawValue + ".section") }
            }
            ForEach(NeedsEventField.allCases, id: \.self) { field in
                DisclosureGroup {
                    EventEditor(input: Binding(get: { draft.events[field] ?? .init() }, set: { draft.set(field, $0) }), language: language)
                    if draft.changedEvents.contains(field) {
                        Button(language.text("不提交此时间事项修改", "Leave this event unchanged")) { draft.leaveEventUnchanged(field) }
                    }
                } label: { NeedsFormLabel(text: field.label(language)) }
            }
            DisclosureGroup {
                ForEach($draft.companions) { $companion in
                    HStack {
                        TextField(language.text("同伴称呼", "Companion label"), text: $companion.label)
                        Button(language.text("移除", "Remove")) { draft.companions.removeAll { $0.id == companion.id } }
                    }
                }
                Button(language.text("添加同伴", "Add companion")) { draft.companions.append(.init()) }
                Text(language.text("移除被固定事项或临时条件引用的同伴时，也需明确修改相应适用对象。", "When removing a referenced companion, explicitly correct the affected items or conditions too.")).font(.footnote)
            } label: { NeedsFormLabel(text: language.text("同伴", "Companions")) }
            DisclosureGroup {
                ForEach($draft.fixedItems) { $item in
                    FixedEditor(item: $item, companions: draft.companions, language: language)
                    Button(language.text("移除此事项", "Remove this item")) { draft.fixedItems.removeAll { $0.id == item.id } }
                    Divider()
                }
                Button(language.text("添加固定事项", "Add fixed item")) { draft.fixedItems.append(.init()) }
            } label: { NeedsFormLabel(text: language.text("已订／固定事项（用户陈述）", "Booked / fixed items (user claims)")) }
            DisclosureGroup {
                ForEach($draft.conditions) { $condition in
                    TextField(language.text("本次条件说明", "Describe this journey condition"), text: $condition.description, axis: .vertical)
                    SubjectsEditor(subjects: $condition.appliesTo, companions: draft.companions, language: language)
                    Button(language.text("移除此条件", "Remove this condition")) { draft.conditions.removeAll { $0.id == condition.id } }
                }
                Button(language.text("添加临时条件", "Add temporary condition")) { draft.conditions.append(.init()) }
            } label: { NeedsFormLabel(text: language.text("本次临时条件", "Temporary journey conditions")) }
        }.disclosureGroupStyle(NeedsDisclosureStyle(language: language))
    }
}

/// Full-width, high-contrast disclosure affordance for the requirements form.
/// The actual label and expanded content remain visible at the user's font size.
public struct NeedsDisclosureStyle: DisclosureGroupStyle {
    private let language: NeedsLanguage
    public init(language: NeedsLanguage) { self.language = language }
    public func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { configuration.isExpanded.toggle() } label: {
                HStack(alignment: .center, spacing: 12) {
                    configuration.label.frame(maxWidth: .infinity, alignment: .leading)
                    Image(systemName: configuration.isExpanded ? "chevron.down" : "chevron.right").foregroundStyle(.primary)
                }.foregroundStyle(.primary).frame(minHeight: 44).contentShape(Rectangle())
            }.buttonStyle(.plain)
                .accessibilityValue(configuration.isExpanded ? language.text("已展开", "Expanded") : language.text("已折叠", "Collapsed"))
            if configuration.isExpanded { configuration.content.padding(.leading, 12) }
        }
    }
}

private struct ObservationEditor: View {
    @Binding var input: NeedsObservationInput
    let language: NeedsLanguage
    var id = "needs.observation"
    var isList = false
    var choices: [(String, String)] = []
    var body: some View {
        VStack(alignment: .leading) {
            Picker(language.text("记录状态", "Recorded state"), selection: $input.state) {
                ForEach(NeedsObservationState.allCases, id: \.self) { state in Text(state.label(language)).tag(state) }
            }.accessibilityIdentifier(id + ".state")
            if input.state == .uncertain {
                TextField(language.text("不确定之处", "What is uncertain"), text: $input.note, axis: .vertical).textFieldStyle(.roundedBorder).accessibilityIdentifier(id + ".note")
            }
            if input.state == .known {
                if isList {
                    ForEach(Array((input.items ?? []).indices), id: \.self) { index in
                        TextField(language.text("包含或不包含的费用", "Included or excluded cost"), text: Binding(
                            get: { input.items?.indices.contains(index) == true ? input.items![index] : "" },
                            set: { value in if input.items?.indices.contains(index) == true { input.items?[index] = value } }
                        ), axis: .vertical)
                        Button(language.text("移除此范围", "Remove this cost entry")) { if input.items?.indices.contains(index) == true { input.items?.remove(at: index) } }
                    }
                    Button(language.text("添加包含或不包含范围", "Add included or excluded cost")) {
                        if input.items == nil { input.items = [] }
                        input.items?.append("")
                    }
                } else if choices.isEmpty {
                    TextField(language.text("用户提供的值", "User-provided value"), text: $input.value, axis: .vertical)
                        .textFieldStyle(.roundedBorder).autocorrectionDisabled().accessibilityIdentifier(id + ".value")
                } else {
                    Picker(language.text("明确选择", "Explicit choice"), selection: $input.value) {
                        Text(language.text("请选择", "Choose")).tag("")
                        ForEach(choices, id: \.0) { Text($0.1).tag($0.0) }
                    }.accessibilityIdentifier(id + ".choice")
                }
            }
        }
    }
}
private struct EventEditor: View {
    @Binding var input: NeedsEventInput
    let language: NeedsLanguage
    var body: some View {
        VStack(alignment: .leading) {
            Text(language.text("当地日期与时间按输入保留；不会随设备时区转换。", "Local date and time stay as entered, regardless of device timezone.")).font(.footnote)
            GroupBox(language.text("当地日期 YYYY-MM-DD", "Local date YYYY-MM-DD")) { ObservationEditor(input: $input.date, language: language) }
            GroupBox(language.text("当地时间 HH:MM[:SS]", "Local time HH:MM[:SS]")) { ObservationEditor(input: $input.time, language: language) }
            GroupBox(language.text("时区 IANA", "Timezone IANA")) { ObservationEditor(input: $input.timezone, language: language) }
            GroupBox(language.text("地点（用户描述）", "Place (user description)")) { ObservationEditor(input: $input.place, language: language) }
            Button(language.text("把本事项未记录的部分明确标记为未提供", "Explicitly mark this event's unrecorded details as missing")) { input.markUnrecordedMissing() }
        }
    }
}
private struct SubjectsEditor: View {
    @Binding var subjects: [String]
    let companions: [NeedsCompanionInput]
    let language: NeedsLanguage
    private var choices: [(String, String)] {
        [("self", language.text("本人", "Self")), ("party", language.text("全体", "Whole party"))] + companions.map { ("companion:" + $0.id, $0.label) }
    }
    var body: some View {
        VStack(alignment: .leading) {
            Text(language.text("适用对象", "Applies to"))
            ForEach(choices, id: \.0) { id, label in
                Toggle(label, isOn: Binding(get: { subjects.contains(id) }, set: { enabled in
                    if enabled { if !subjects.contains(id) { subjects.append(id) } } else { subjects.removeAll { $0 == id } }
                }))
            }
            ForEach(subjects.filter { s in !choices.contains { $0.0 == s } }, id: \.self) { subject in
                Text(language.text("已移除的同伴引用：", "Removed companion reference: ") + subject)
                Button(language.text("明确移除该引用", "Explicitly remove this reference")) { subjects.removeAll { $0 == subject } }
            }
        }
    }
}
private struct FixedEditor: View {
    @Binding var item: NeedsFixedInput
    let companions: [NeedsCompanionInput]
    let language: NeedsLanguage
    var body: some View {
        VStack(alignment: .leading) {
            Picker(language.text("事项类型", "Item type"), selection: $item.kind) {
                Text(language.text("请选择", "Choose")).tag(Optional<NeedsSchema.NeedsFixedItem.kindPayload>.none)
                Text(language.text("酒店", "Hotel")).tag(Optional(NeedsSchema.NeedsFixedItem.kindPayload.hotel))
                Text(language.text("交通", "Transport")).tag(Optional(NeedsSchema.NeedsFixedItem.kindPayload.transport))
                Text(language.text("预约", "Appointment")).tag(Optional(NeedsSchema.NeedsFixedItem.kindPayload.appointment))
                Text(language.text("意向", "Intent")).tag(Optional(NeedsSchema.NeedsFixedItem.kindPayload.intent))
            }
            TextField(language.text("事项说明", "Item description"), text: $item.description, axis: .vertical)
            SubjectsEditor(subjects: $item.appliesTo, companions: companions, language: language)
            GroupBox(language.text("固定意图", "Lock intent")) {
                ObservationEditor(input: $item.locked, language: language, choices: [("true", language.text("固定", "Locked")), ("false", language.text("可调整", "Flexible"))])
            }
            GroupBox(language.text("用户声称的预订状态（未核实）", "Reported booking status (unverified)")) {
                ObservationEditor(input: $item.booking, language: language, choices: [("booked", language.text("已订", "Booked")), ("intended", language.text("计划预订", "Intended")), ("cancelled", language.text("已取消", "Cancelled"))])
            }
            DisclosureGroup(language.text("开始", "Start")) { EventEditor(input: $item.start, language: language) }
            DisclosureGroup(language.text("结束", "End")) { EventEditor(input: $item.end, language: language) }
        }
    }
}

public struct NeedsDetailsView: View {
    public let fields: NeedsSchema.NeedsFields
    public let version: Int?
    public let language: NeedsLanguage
    private let unconfirmed: Bool
    private let prefix: String
    public init(fields: NeedsSchema.NeedsFields, version: Int, language: NeedsLanguage, identifierPrefix: String = "needs.detail") {
        self.fields = fields; self.version = version; self.language = language; unconfirmed = false; prefix = identifierPrefix
    }
    public init(unconfirmedFields: NeedsSchema.NeedsFields, language: NeedsLanguage, identifierPrefix: String = "needs.preview") {
        fields = unconfirmedFields; version = nil; self.language = language; unconfirmed = true; prefix = identifierPrefix
    }
    // Conversion for display only. No action, expected-version claim or writer is exposed.
    private var display: NeedsDraft { .init(needsID: "display", expectedVersion: 0, fields: fields) }
    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let version { Text(language.text("读取的版本 ", "Version at read: ") + String(version)).font(.headline).accessibilityIdentifier(prefix + ".version") }
            Text(unconfirmed
                ? language.text("来源：合成提取候选，尚未确认或保存。预订和时间未由外部服务核实。", "Source: synthetic extraction candidates, unconfirmed and unsaved. Bookings and times are not externally verified.")
                : language.text("来源：用户提供；预订和时间未由外部服务核实。", "Source: user provided; bookings and times are not externally verified."))
                .font(.footnote).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier(prefix + ".source")
            ForEach(NeedsField.allCases, id: \.self) { field in
                row(field.label(language), summary(display.observations[field]!, choice: field == .basis ? "basis" : ""), prefix + "." + field.rawValue)
            }
            ForEach(NeedsEventField.allCases, id: \.self) { field in
                GroupBox(field.label(language)) {
                    if let event = display.events[field] { eventSummary(event, id: prefix + "." + field.rawValue) }
                    else { Text(NeedsObservationState.absent.label(language)).accessibilityIdentifier(prefix + "." + field.rawValue) }
                }
            }
            GroupBox(language.text("同伴", "Companions")) {
                if let companions = fields.companions?.additionalProperties {
                    if companions.isEmpty { Text(language.text("明确为空", "Explicitly empty")) }
                    ForEach(companions.keys.sorted(), id: \.self) { id in
                        Text(companions[id]!).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier(prefix + ".companion." + id)
                    }
                } else { Text(NeedsObservationState.absent.label(language)) }
            }
            GroupBox(language.text("固定事项（非查证订单）", "Fixed items (not verified orders)")) {
                if let items = fields.fixed_items {
                    if items.isEmpty { Text(language.text("明确为空", "Explicitly empty")) }
                    ForEach(Array(items.enumerated()), id: \.element.item_id) { index, item in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(item.description).font(.headline).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier(prefix + ".fixed.\(index).description")
                            Text(kindLabel(item.kind)).accessibilityIdentifier(prefix + ".fixed.\(index).kind")
                            row(language.text("适用对象", "Applies to"), subjects(item.applies_to), prefix + ".fixed.\(index).subjects")
                            row(language.text("固定意图", "Lock intent"), summary(.init(item.locked), choice: "lock"), prefix + ".fixed.\(index).locked")
                            row(language.text("预订声称（未核实）", "Booking claim (unverified)"), summary(.init(item.booking_status), choice: "booking"), prefix + ".fixed.\(index).booking")
                            Text(language.text("开始", "Start")); eventSummary(.init(item.start), id: prefix + ".fixed.\(index).start")
                            Text(language.text("结束", "End")); eventSummary(.init(item.end), id: prefix + ".fixed.\(index).end")
                        }.padding(.vertical, 6)
                    }
                } else { Text(NeedsObservationState.absent.label(language)) }
            }
            GroupBox(language.text("仅本次的临时条件", "Temporary conditions for this trip only")) {
                if let items = fields.temporary_conditions {
                    if items.isEmpty { Text(language.text("明确为空", "Explicitly empty")) }
                    ForEach(Array(items.enumerated()), id: \.element.condition_id) { index, item in
                        Text(item.description + " · " + subjects(item.applies_to)).fixedSize(horizontal: false, vertical: true)
                            .accessibilityIdentifier(prefix + ".temporary.\(index)")
                    }
                } else { Text(NeedsObservationState.absent.label(language)) }
            }
        }.foregroundStyle(.primary).textSelection(.enabled)
    }
    private func row(_ title: String, _ value: String, _ id: String) -> some View {
        NeedsSelectableFieldText(text: title + "\n" + value)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).accessibilityIdentifier(id)
    }
    private func summary(_ input: NeedsObservationInput, choice: String = "") -> String {
        switch input.state {
        case .known:
            var value = input.value
            if let items = input.items { value = items.isEmpty ? language.text("明确为空", "Explicitly empty") : items.joined(separator: "; ") }
            if choice == "lock" { value = input.value == "true" ? language.text("固定", "Locked") : language.text("可调整", "Flexible") }
            if choice == "booking" { value = ["booked": language.text("已订", "Booked"), "intended": language.text("计划预订", "Intended"), "cancelled": language.text("已取消", "Cancelled")][input.value] ?? input.value }
            if choice == "basis", input.value == "total" { value = language.text("总计", "Total") }
            if choice == "basis", input.value == "per_person" { value = language.text("每人", "Per person") }
            return (unconfirmed ? language.text("未确认候选", "Unconfirmed candidate") : input.state.label(language)) + ": " + value
        case .uncertain: return input.state.label(language) + ": " + input.note
        default: return input.state.label(language)
        }
    }
    private func kindLabel(_ kind: NeedsSchema.NeedsFixedItem.kindPayload) -> String {
        switch kind {
        case .hotel: language.text("酒店", "Hotel")
        case .transport: language.text("交通", "Transport")
        case .appointment: language.text("预约", "Appointment")
        case .intent: language.text("意向", "Intent")
        }
    }
    private func subjects(_ values: [String]) -> String {
        values.map { value in
            if value == "self" { return language.text("本人", "Self") }
            if value == "party" { return language.text("全体", "Whole party") }
            return fields.companions?.additionalProperties[String(value.dropFirst(10))] ?? value
        }.joined(separator: ", ")
    }
    private func eventSummary(_ event: NeedsEventInput, id: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            row(language.text("当地日期", "Local date"), summary(event.date), id + ".date")
            row(language.text("当地时间", "Local time"), summary(event.time), id + ".time")
            row(language.text("明确时区", "Declared timezone"), summary(event.timezone), id + ".timezone")
            row(language.text("地点", "Place"), summary(event.place), id + ".place")
        }
    }
}

// Domain-local adaptation of the existing audited RunSelectableText measurement.
// Keep selection and the full visible label/value, without stale offscreen
// SwiftUI Text accessibility frames during dynamic-type/contrast auditing.
#if os(iOS)
import UIKit
private struct NeedsSelectableFieldText: UIViewRepresentable {
    let text: String
    @Environment(\.dynamicTypeSize) private var size
    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false; view.isSelectable = true; view.isScrollEnabled = false
        view.dataDetectorTypes = []; view.backgroundColor = .clear; view.textColor = .label
        view.textContainerInset = .zero; view.textContainer.lineFragmentPadding = 0
        view.adjustsFontForContentSizeCategory = true
        view.setContentCompressionResistancePriority(.required, for: .vertical)
        return view
    }
    func updateUIView(_ view: UITextView, context: Context) {
        if view.text?.utf8.elementsEqual(text.utf8) != true { view.text = text }
        view.font = UIFont.preferredFont(forTextStyle: .body,
            compatibleWith: UITraitCollection(preferredContentSizeCategory: category))
        // The spoken text is exactly the visible text; no alternate audit value.
        view.accessibilityLabel = text; view.accessibilityValue = nil
    }
    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UITextView, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    static func dismantleUIView(_ view: UITextView, coordinator: ()) { view.text = nil; view.accessibilityLabel = nil }
    private var category: UIContentSizeCategory { needsUIContentSize(size) }

}
#else
private struct NeedsSelectableFieldText: View {
    let text: String
    var body: some View { Text(text).foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true) }
}
#endif

#if os(iOS)
public struct NeedsFormLabel: UIViewRepresentable {
    private let text: String
    @Environment(\.dynamicTypeSize) private var size
    public init(text: String) { self.text = text }
    public func makeUIView(context: Context) -> UILabel {
        let view = UILabel(); view.numberOfLines = 0; view.lineBreakMode = .byWordWrapping
        view.textColor = .label; view.adjustsFontForContentSizeCategory = true
        view.setContentCompressionResistancePriority(.required, for: .vertical)
        return view
    }
    public func updateUIView(_ view: UILabel, context: Context) {
        view.text = text
        view.font = UIFont.preferredFont(forTextStyle: .body, compatibleWith: UITraitCollection(preferredContentSizeCategory: needsUIContentSize(size)))
    }
    public func sizeThatFits(_ proposal: ProposedViewSize, uiView: UILabel, context: Context) -> CGSize? {
        guard let width = proposal.width, width.isFinite, width > 0 else { return nil }
        return uiView.sizeThatFits(CGSize(width: width, height: .greatestFiniteMagnitude))
    }
    public static func dismantleUIView(_ view: UILabel, coordinator: ()) { view.text = nil }
}
private func needsUIContentSize(_ size: DynamicTypeSize) -> UIContentSizeCategory {
    switch size {
    case .xSmall: .extraSmall
    case .small: .small
    case .medium: .medium
    case .large: .large
    case .xLarge: .extraLarge
    case .xxLarge: .extraExtraLarge
    case .xxxLarge: .extraExtraExtraLarge
    case .accessibility1: .accessibilityMedium
    case .accessibility2: .accessibilityLarge
    case .accessibility3: .accessibilityExtraLarge
    case .accessibility4: .accessibilityExtraExtraLarge
    case .accessibility5: .accessibilityExtraExtraExtraLarge
    @unknown default: .large
    }
}
#else
public struct NeedsFormLabel: View {
    private let text: String
    public init(text: String) { self.text = text }
    public var body: some View { Text(text).foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true) }
}
#endif
