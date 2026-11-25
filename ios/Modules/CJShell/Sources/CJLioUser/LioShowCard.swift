#if os(iOS)
import CJRunClient
import SwiftUI
import UIKit

/// The full-screen card a traveller turns towards someone (#1572): Chinese large, English small, screen kept awake.
/// Same layout as the driver sign (#1550); accessibility identifiers are `<prefix>.request`, `<prefix>.name`,
/// `<prefix>.address`, `<prefix>.english`, `<prefix>.note` and `<prefix>.done`, matching the driver sign's.
/// An optional accessory (for example the ordering card's note checklist) sits under the card.
struct LioShowCardSheet<Accessory: View>: View {
    let language: LioLanguage
    let content: LioShowCardContent
    var title: String?
    var identifierPrefix = "lio.show-card.sheet"
    @ViewBuilder var accessory: () -> Accessory
    @Environment(\.dismiss) private var dismiss
    @State private var priorIdleTimer: Bool?

    init(language: LioLanguage, content: LioShowCardContent, title: String? = nil,
         identifierPrefix: String = "lio.show-card.sheet", @ViewBuilder accessory: @escaping () -> Accessory) {
        self.language = language
        self.content = content
        self.title = title
        self.identifierPrefix = identifierPrefix
        self.accessory = accessory
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                    LioShowCardFace(content: content, identifierPrefix: identifierPrefix)
                        .textSelection(.enabled)
                    accessory()
                }
                .padding(LioTheme.Spacing.lg)
            }
            .background(LioTheme.paper)
            .foregroundStyle(LioTheme.ink)
            .navigationTitle(title ?? language.text("Show this card", "出示给对方"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    // Navigation-bar text does not follow Dynamic Type; this label does.
                    Button { dismiss() } label: {
                        RunReadableText(text: language.text("Close", "关闭"), color: LioTheme.vermilion).fixedSize()
                            .frame(minHeight: 44)
                    }
                    .accessibilityLabel(language.text("Close", "关闭"))
                    .accessibilityIdentifier(identifierPrefix + ".done")
                }
            }
        }
        .tint(LioTheme.vermilion)
        .onAppear {
            guard priorIdleTimer == nil else { return }
            priorIdleTimer = UIApplication.shared.isIdleTimerDisabled
            UIApplication.shared.isIdleTimerDisabled = true
        }
        .onDisappear {
            if let priorIdleTimer {
                UIApplication.shared.isIdleTimerDisabled = priorIdleTimer
                self.priorIdleTimer = nil
            }
        }
    }
}

extension LioShowCardSheet where Accessory == EmptyView {
    init(language: LioLanguage, content: LioShowCardContent, title: String? = nil,
         identifierPrefix: String = "lio.show-card.sheet") {
        self.init(language: language, content: content, title: title, identifierPrefix: identifierPrefix) { EmptyView() }
    }
}

/// The card's text, used full screen and as the smaller preview while filling in details.
struct LioShowCardFace: View {
    let content: LioShowCardContent
    var compact = false
    var identifierPrefix = "lio.show-card.sheet"

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 10 : 18) {
            if let lead = content.leadZH {
                Text(lead).font((compact ? Font.subheadline : .title3).weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier(identifierPrefix + ".request")
            }
            Text(content.mainZH)
                .font(compact ? LioTheme.display(.title2).weight(.bold) : LioTheme.display(.largeTitle).weight(.bold))
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier(identifierPrefix + ".name")
            // One text per block, so UI tests read `<prefix>.address` as a static text (the driver sign's address).
            if !content.detailsZH.isEmpty {
                Text(content.detailsZH.joined(separator: "\n"))
                    .font((compact ? Font.headline : .title2).weight(.semibold))
                    .lineSpacing(compact ? 4 : 8)
                    .accessibilityIdentifier(identifierPrefix + ".address")
            }
            if !content.english.isEmpty {
                Text(content.english.joined(separator: "\n"))
                    .font(compact ? .footnote : .body)
                    .lineSpacing(4)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier(identifierPrefix + ".english")
            }
            if let noteZH = content.noteZH {
                VStack(alignment: .leading, spacing: 4) {
                    Text(noteZH).font(.footnote.weight(.semibold))
                    if let noteEN = content.noteEN { Text(noteEN).font(.footnote) }
                }
                .foregroundStyle(LioTheme.inkSecondary)
                .padding(LioTheme.Spacing.sm)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(identifierPrefix + ".note")
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Scenes and their cards (#1572). Details typed here stay on this screen; the hotel and room come from
/// the saved stay hotel (#1573).
struct LioShowCardsView: View {
    let language: LioLanguage
    let hotel: LioStayHotel?
    @State private var input: LioShowCardInput

    init(language: LioLanguage, hotel: LioStayHotel?) {
        self.language = language
        self.hotel = hotel
        var input = LioShowCardInput(hotel: hotel?.showCardHotel)
        input.roomNumber = hotel?.roomNumber
        _input = State(initialValue: input)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
                Text(language.text("Pick a card, add your details, then turn the screen towards the other person.",
                                   "选一张卡，填上你的信息，再把屏幕转给对方看。"))
                    .font(.subheadline)
                    .foregroundStyle(LioTheme.inkSecondary)
                ForEach(LioShowCardScene.allCases) { scene in
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        Label(scene.title(language), systemImage: scene.symbol)
                            .font(.headline)
                            .foregroundStyle(LioTheme.ink)
                            .accessibilityAddTraits(.isHeader)
                        VStack(spacing: 0) {
                            ForEach(Array(scene.cards.enumerated()), id: \.element) { index, kind in
                                NavigationLink {
                                    LioShowCardEditor(language: language, kind: kind, input: $input)
                                } label: {
                                    row(kind)
                                }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier(kind.identifier)
                                if index < scene.cards.count - 1 {
                                    Divider().padding(.leading, LioTheme.Spacing.md)
                                }
                            }
                        }
                        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                    }
                }
            }
            .padding(LioTheme.Spacing.md)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Show Cards", "出示卡"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
    }

    private func row(_ kind: LioShowCardKind) -> some View {
        HStack(spacing: LioTheme.Spacing.sm) {
            VStack(alignment: .leading, spacing: 2) {
                Text(kind.title(language)).foregroundStyle(LioTheme.ink)
                Text(kind.content(input).mainZH)
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
                .accessibilityHidden(true)
        }
        .padding(.horizontal, LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, minHeight: 56, alignment: .leading)
        .contentShape(Rectangle())
    }
}

/// One card: its details, a live preview, and the button that shows it full screen.
struct LioShowCardEditor: View {
    let language: LioLanguage
    let kind: LioShowCardKind
    @Binding var input: LioShowCardInput
    @Environment(\.lioMedicalCard) private var medicalCard
    @State private var showing = false
    @State private var showsMedicalCard = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                LioShowCardFace(content: kind.content(input), compact: true, identifierPrefix: "lio.show-card.preview")
                    .padding(LioTheme.Spacing.md)
                    .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                Button {
                    showing = true
                } label: {
                    Label(language.text("Show full screen", "全屏出示"), systemImage: "arrow.up.left.and.arrow.down.right")
                }
                .buttonStyle(LioPrimaryButtonStyle())
                .accessibilityIdentifier("lio.show-card.show")
                ForEach(kind.fields, id: \.self) { field in
                    fieldView(field)
                }
                if kind.scene == .pharmacy, let medicalCard, medicalCard.isCurrent() {
                    Button {
                        showsMedicalCard = true
                    } label: {
                        Label(language.text("Show my medical card", "出示我的医疗卡"), systemImage: "cross.case")
                            .frame(minHeight: 44)
                    }
                    .accessibilityIdentifier("lio.show-card.medical-card")
                }
            }
            .padding(LioTheme.Spacing.md)
        }
        .background(LioTheme.paper)
        .foregroundStyle(LioTheme.ink)
        .navigationTitle(kind.title(language))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
        .fullScreenCover(isPresented: $showing) {
            LioShowCardSheet(language: language, content: kind.content(input), title: kind.title(language))
        }
        .fullScreenCover(isPresented: $showsMedicalCard) {
            if let medicalCard {
                NavigationStack {
                    LioMedicalCardView(language: language, storage: medicalCard, opensDisplay: true)
                }
            }
        }
    }

    @ViewBuilder private func fieldView(_ field: LioShowCardField) -> some View {
        switch field {
        case .bookingName:
            text(language.text("Name on the booking (as in your passport)", "预订姓名（与护照一致）"), $input.bookingName)
        case .nights:
            Stepper(value: $input.nights, in: 1...30) {
                Text(language.text("Extra nights: \(input.nights)", "续住：\(input.nights) 晚"))
            }
            .frame(minHeight: 44)
        case .roomNumber:
            text(language.text("Room number", "房间号"), $input.roomNumber, keyboard: .numbersAndPunctuation)
        case .pickUpTime:
            text(language.text("Back to collect at (e.g. 18:00)", "回来取的时间（如 18:00）"), $input.pickUpTime,
                 keyboard: .numbersAndPunctuation)
        case .destination:
            text(language.text("Destination (Chinese name works best)", "目的地（最好写中文名）"), $input.destinationZH)
        case .symptoms:
            multiSelect(language.text("Symptoms", "症状"), LioSymptom.allCases, $input.symptoms) {
                language == .chinese ? $0.chinese : $0.english
            }
        case .symptomDays:
            picker(language.text("How long", "持续多久"), LioSymptomDays.allCases, optional: $input.symptomDays) {
                language == .chinese ? $0.chinese : $0.english
            }
        case .medicineName:
            text(language.text("Medicine name or ingredient (copy it from the box)", "药名或成分（照包装抄写）"),
                 $input.medicineName)
        case .drugAllergies:
            multiSelect(language.text("Allergic to", "过敏的药物"), LioDrugAllergen.allCases, $input.drugAllergies) {
                language == .chinese ? $0.chinese : $0.english
            }
        case .spice:
            Picker(language.text("Spice", "辣度"), selection: $input.spice) {
                ForEach(LioSpiceLevel.allCases) { Text($0.title(language)).tag($0) }
            }
            .pickerStyle(.segmented)
        case .foodAllergies:
            multiSelect(language.text("Allergic to", "过敏的食物"), LioFoodAllergen.allCases, $input.foodAllergies) {
                language == .chinese ? $0.chinese : $0.english
            }
        case .place:
            text(language.text("Place (Chinese name works best)", "地点（最好写中文名）"), $input.placeZH)
        case .nearest:
            picker(language.text("Looking for", "要找"), LioNearestPlace.allCases, selection: $input.nearest) {
                language == .chinese ? $0.chinese : $0.english.capitalized
            }
        case .hotel:
            if let hotel = input.hotel {
                Label(hotel.nameZH, systemImage: "bed.double").font(.subheadline)
            } else {
                Text(language.text("Set your hotel in Back to Hotel to add its address here.",
                                   "在「回酒店」里设置酒店后，这里会带上酒店地址。"))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
        case .amount:
            text(language.text("Amount", "金额"), $input.amount, keyboard: .decimalPad)
        case .currency:
            picker(language.text("Currency", "币种"), LioExchangeCurrency.allCases, selection: $input.currency) {
                language == .chinese ? $0.chinese : $0.english.capitalized
            }
        case .atmLocation:
            text(language.text("Where is the ATM", "ATM 位置"), $input.atmLocation)
        }
    }

    private func text(_ title: String, _ value: Binding<String?>, keyboard: UIKeyboardType = .default) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
            TextField(title, text: Binding(get: { value.wrappedValue ?? "" }, set: { value.wrappedValue = $0 }))
                .keyboardType(keyboard)
                .textFieldStyle(.roundedBorder)
                .frame(minHeight: 44)
        }
    }

    private func multiSelect<Item: Identifiable & Hashable>(_ title: String, _ items: [Item], _ selection: Binding<Set<Item>>,
                                                             label: @escaping (Item) -> String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).font(.subheadline).foregroundStyle(LioTheme.inkSecondary).padding(.bottom, 4)
            ForEach(items) { item in
                Button {
                    if selection.wrappedValue.contains(item) { selection.wrappedValue.remove(item) }
                    else { selection.wrappedValue.insert(item) }
                } label: {
                    HStack {
                        Text(label(item)).foregroundStyle(LioTheme.ink)
                        Spacer()
                        Image(systemName: selection.wrappedValue.contains(item) ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(selection.wrappedValue.contains(item) ? LioTheme.vermilion : LioTheme.inkSecondary)
                            .accessibilityHidden(true)
                    }
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selection.wrappedValue.contains(item) ? [.isSelected] : [])
            }
        }
    }

    private func picker<Item: Identifiable & Hashable>(_ title: String, _ items: [Item], selection: Binding<Item>,
                                                       label: @escaping (Item) -> String) -> some View {
        HStack {
            Text(title).foregroundStyle(LioTheme.inkSecondary)
            Spacer()
            Picker(title, selection: selection) {
                ForEach(items) { Text(label($0)).tag($0) }
            }
        }
        .frame(minHeight: 44)
    }

    private func picker<Item: Identifiable & Hashable>(_ title: String, _ items: [Item], optional: Binding<Item?>,
                                                       label: @escaping (Item) -> String) -> some View {
        HStack {
            Text(title).foregroundStyle(LioTheme.inkSecondary)
            Spacer()
            Picker(title, selection: optional) {
                Text(language.text("Not given", "不填")).tag(Item?.none)
                ForEach(items) { Text(label($0)).tag(Optional($0)) }
            }
        }
        .frame(minHeight: 44)
    }
}
#endif
