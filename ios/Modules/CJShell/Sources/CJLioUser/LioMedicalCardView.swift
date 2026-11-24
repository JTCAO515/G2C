#if os(iOS)
import CJRunClient
import SwiftUI

private enum LioMedicalCardStorageKey: EnvironmentKey {
    static let defaultValue: LocalMedicalCardStorage? = nil
}

extension EnvironmentValues {
    var lioMedicalCard: LocalMedicalCardStorage? {
        get { self[LioMedicalCardStorageKey.self] }
        set { self[LioMedicalCardStorageKey.self] = newValue }
    }
}

public extension View {
    func lioMedicalCardStorage(_ storage: LocalMedicalCardStorage?) -> some View {
        environment(\.lioMedicalCard, storage)
    }
}

struct LioMedicalCardView: View {
    let language: LioLanguage
    let storage: LocalMedicalCardStorage
    let opensDisplay: Bool

    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focusedField: LocalMedicalCard.Field?
    @State private var draft: LocalMedicalCard?
    @State private var loaded = false
    @State private var showCard = false
    @State private var problem = false
    @State private var saved = false

    private var title: String { language.text("Medical card", "医疗卡") }

    var body: some View {
        Group {
            if showCard, let draft, storage.isCurrent(), scenePhase == .active {
                display(draft)
            } else {
                editor
            }
        }
        .navigationTitle(showCard ? "医疗卡 / Medical card" : title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                RunReadableText(text: showCard ? "医疗卡 / Medical card" : title,
                                style: .headline, color: LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
            }
            if !showCard {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Close", "关闭")) { dismiss() }
                }
            }
            ToolbarItem(placement: .confirmationAction) {
                if showCard {
                    Button {
                        showCard = false
                    } label: {
                        RunReadableText(text: language.text("Done", "完成"), color: LioTheme.ink)
                            .frame(minWidth: 44, minHeight: 44)
                    }
                } else if draft != nil && !problem {
                    Button(language.text("Save", "保存"), action: save)
                        .accessibilityLabel(language.text("Save on this phone", "保存到这台手机"))
                }
            }
        }
        .tint(LioTheme.ink)
        .privacySensitive()
        .task { load() }
        .onChange(of: scenePhase) { _, phase in
            if phase != .active {
                showCard = false
                draft = nil
                loaded = false
                dismiss()
            }
        }
        .alert(language.text("Medical card saved on this device.", "医疗卡已保存在这台设备上。"), isPresented: $saved) {
            Button(language.text("OK", "好"), role: .cancel) {}
        }
    }

    private var editor: some View {
        Form {
            if problem {
                Text(language.text("The medical card is unavailable on this device.", "这台设备暂时无法使用医疗卡。"))
                    .foregroundStyle(LioTheme.ink)
                Button(language.text("Try again", "重试"), action: load)
            } else if storage.isCurrent(), scenePhase == .active {
                if !loaded {
                    ProgressView()
                } else if draft != nil {
                    fields
                } else {
                    disclosure
                }
            }
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private var disclosure: some View {
        Section {
            Text(language.text(
                "Your medical card stays on this phone. We can’t see it. It won’t move to a new phone. Keep a separate copy of important information.",
                "医疗卡只存在这台手机上，我们看不到。换手机后不会迁移，请单独备份重要信息。"))
            Button(language.text("I understand", "我已了解")) {
                let initial = LocalMedicalCard()
                do {
                    try storage.save(initial)
                    draft = initial
                } catch { problem = true }
            }
        }
    }

    @ViewBuilder private var fields: some View {
        Section {
            Button(language.text("Show medical card", "出示医疗卡")) { showCard = true }
                .disabled(draft?.isEmpty != false)
            Button(language.text("Clear card", "清空医疗卡"), role: .destructive, action: clear)
        }
        Section {
            Text(language.text("All fields are optional.", "所有内容均可选填。"))
            ForEach(LocalMedicalCard.Field.allCases) { field in
                TextField(field.title(language), text: Binding(
                    get: { draft?[field] ?? "" },
                    set: { draft?[field] = String($0.prefix(field.limit)) }
                ), axis: .vertical)
                .focused($focusedField, equals: field)
                .accessibilityIdentifier("lio.medical-card.field." + field.rawValue)
            }
        }
    }

    private func display(_ card: LocalMedicalCard) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                ForEach(LocalMedicalCard.Field.allCases.filter { !card[$0].isEmpty }) { field in
                    VStack(alignment: .leading, spacing: 6) {
                        RunReadableText(text: field.title(.chinese) + " / " + field.title(.english),
                                        style: .headline, color: LioTheme.ink)
                        RunReadableText(text: card[field], style: .body, color: LioTheme.ink)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(24)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
    }

    private func load() {
        guard storage.isCurrent(), scenePhase == .active else { return }
        do {
            draft = try storage.load()
            loaded = true
            problem = false
            if opensDisplay && draft?.isEmpty == false { showCard = true }
        } catch {
            draft = nil
            problem = true
        }
    }

    private func save() {
        guard let draft, scenePhase == .active else { return }
        focusedField = nil
        do {
            try storage.save(draft)
            saved = true
        } catch { problem = true }
    }

    private func clear() {
        do {
            try storage.clear()
            draft = nil
            problem = false
        } catch {
            draft = nil
            problem = true
        }
    }
}

private extension LocalMedicalCard.Field {
    func title(_ language: LioLanguage) -> String {
        switch self {
        case .bloodType: language.text("Blood type", "血型")
        case .drugAllergies: language.text("Medication allergies", "药物过敏")
        case .foodAllergies: language.text("Food allergies", "食物过敏")
        case .otherAllergies: language.text("Other allergies", "其他过敏")
        case .medications: language.text("Current medications", "正在服用的药")
        case .medicalHistory: language.text("Chronic conditions or medical history", "慢性病或重要病史")
        case .contactName: language.text("Emergency contact name", "紧急联系人姓名")
        case .contactRelationship: language.text("Relationship to you", "与你的关系")
        case .contactPhone: language.text("Emergency contact phone", "紧急联系人电话")
        case .insurer: language.text("Insurance company", "保险公司")
        case .policyNumber: language.text("Policy number", "保单号")
        }
    }
}
#endif
