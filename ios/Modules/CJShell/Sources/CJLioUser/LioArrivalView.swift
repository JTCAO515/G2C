#if os(iOS)
import SwiftUI

/// Arrival mode: the first hours in China as a checklist. Every step opens the tool that does it and can be ticked.
/// Shown only when `G2CArrivalModeEnabled` is YES (see `LioArrivalFeature`).
struct LioArrivalView: View {
    let language: LioLanguage
    /// The trip's stays, if there is a trip; the taxi step uses the first matched address.
    var hotels: [LioRichItinerary.Hotel] = []
    /// The trip's first day, if known; otherwise today.
    var arrival: Date?
    var rules: LioArrivalRules? = try? LioArrivalRules.bundled()
    @AppStorage("lio.arrival.progress.v1") private var storedProgress = ""

    private var progress: LioArrivalProgress { LioArrivalProgress(stored: storedProgress) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                Text(language.text("\(progress.doneCount) of \(LioArrivalStep.allCases.count) done",
                                   "已完成 \(progress.doneCount)/\(LioArrivalStep.allCases.count)"))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.arrival.progress")
                ForEach(LioArrivalStep.allCases) { step in
                    LioArrivalStepRow(step: step, language: language, done: progress.isDone(step), toggle: {
                        var next = progress
                        next.toggle(step)
                        storedProgress = next.stored
                    }) {
                        destination(step)
                    }
                }
            }
            .padding(.horizontal, LioTheme.Spacing.md)
            .padding(.vertical, 18)
        }
        .background(LioTheme.paper)
        .navigationTitle(language.text("Arrival Mode", "落地模式"))
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder private func destination(_ step: LioArrivalStep) -> some View {
        switch step {
        case .entry: LioArrivalEntryView(language: language, rules: rules, arrival: arrival ?? .now)
        case .payment: LioPaymentGuideView(language: language)
        case .internet: LioArrivalInternetView(language: language)
        case .taxi: LioArrivalTaxiView(language: language, tripHotel: LioArrivalHotel(hotels: hotels))
        case .emergency: LioLocalSupportView(language: language)
        }
    }
}

private struct LioArrivalStepRow<Destination: View>: View {
    let step: LioArrivalStep
    let language: LioLanguage
    let done: Bool
    let toggle: () -> Void
    @ViewBuilder let destination: () -> Destination

    var body: some View {
        HStack(alignment: .center, spacing: LioTheme.Spacing.sm) {
            Button(action: toggle) {
                Image(systemName: done ? "checkmark.circle.fill" : "circle")
                    .font(.title2)
                    .foregroundStyle(done ? LioTheme.jade : LioTheme.inkSecondary)
                    .frame(minWidth: 44, minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(step.title(language))
            .accessibilityValue(done ? language.text("Done", "已完成") : language.text("Not done", "未完成"))
            .accessibilityIdentifier(step.identifier + ".tick")

            NavigationLink(destination: destination) {
                HStack(spacing: LioTheme.Spacing.sm) {
                    Image(systemName: step.symbol)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(LioTheme.vermilion)
                        .frame(width: 32, height: 32)
                        .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                        Text(step.title(language)).font(.headline).foregroundStyle(LioTheme.ink)
                            .strikethrough(done, color: LioTheme.inkSecondary)
                        Text(step.summary(language)).font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.footnote.weight(.semibold))
                        .foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
                }
                .multilineTextAlignment(.leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(step.identifier)
        }
        .padding(.vertical, LioTheme.Spacing.sm)
        .padding(.trailing, LioTheme.Spacing.md)
        .padding(.leading, LioTheme.Spacing.xxs)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

// MARK: - Step 1: entry rules and the official arrival card

struct LioArrivalEntryView: View {
    let language: LioLanguage
    let rules: LioArrivalRules?
    @AppStorage("lio.local-support.nationality") private var nationality = ""
    @State private var otherNationality = false
    @State private var arrival: Date
    @State private var stayDays = 7
    @State private var onward = false

    init(language: LioLanguage, rules: LioArrivalRules?, arrival: Date) {
        self.language = language
        self.rules = rules
        _arrival = State(initialValue: arrival)
    }

    private static let other = "OTHER"

    private var selection: Binding<String> {
        Binding(get: {
            if otherNationality { return Self.other }
            return rules?.country(nationality) != nil ? nationality : (nationality.isEmpty ? "" : Self.other)
        }, set: { value in
            otherNationality = value == Self.other
            // The nationality is shared with Local Support's embassy card; "other" leaves that choice alone.
            if value != Self.other { nationality = value }
        })
    }

    private var trip: LioArrivalTrip {
        LioArrivalTrip(countryCode: selection.wrappedValue, arrival: LioArrivalDay(date: arrival),
                       stayDays: stayDays, onwardToThirdCountry: onward)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                form
                if let rules, !selection.wrappedValue.isEmpty {
                    LioArrivalDecisionCard(language: language, rules: rules,
                                           decision: rules.evaluate(trip, today: LioArrivalDay(date: .now)))
                }
                arrivalCard
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(LioArrivalStep.entry.title(language))
        .navigationBarTitleDisplayMode(.inline)
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            LabeledContent(language.text("Passport", "护照国籍")) {
                Picker(language.text("Passport", "护照国籍"), selection: selection) {
                    Text(language.text("Choose", "请选择")).tag("")
                    ForEach(rules?.countries ?? [], id: \.code) { country in
                        Text(country.name.text(language)).tag(country.code)
                    }
                    Text(language.text("Other", "其他国籍")).tag(Self.other)
                }
                .labelsHidden()
                .accessibilityIdentifier("lio.arrival.nationality")
            }
            DatePicker(language.text("Arrival day", "入境日期"), selection: $arrival, displayedComponents: .date)
                .accessibilityIdentifier("lio.arrival.date")
            Stepper(value: $stayDays, in: 1...90) {
                Text(language.text("Days in China: \(stayDays)", "在华停留：\(stayDays) 天"))
            }
            .accessibilityIdentifier("lio.arrival.days")
            Toggle(language.text("Flying on to a third country or region (not back where you came from)",
                                 "离境后前往第三国（地区），不是返回出发地"), isOn: $onward)
                .accessibilityIdentifier("lio.arrival.onward")
        }
        .foregroundStyle(LioTheme.ink)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var arrivalCard: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Text(language.text("Arrival card", "入境卡")).font(.headline)
            if let notice = rules?.arrivalCard {
                Text(notice.summary.text(language)).font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
            // The only link this step opens for the card: fixed in code to the NIA page (LioArrivalCard).
            Link(destination: LioArrivalCard.officialURL) {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    Label(language.text("Fill it in on the official NIA page", "去国家移民管理局官方页面填写"),
                          systemImage: "arrow.up.right.square")
                        .font(.body.weight(.semibold))
                    Text(LioArrivalCard.officialURL.host ?? "").font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .foregroundStyle(LioTheme.vermilion)
            .accessibilityIdentifier("lio.arrival.card.official")
            if let notice = rules?.arrivalCard {
                LioArrivalSources(language: language, sources: notice.sources, checkedAt: notice.checkedAt)
            }
        }
        .foregroundStyle(LioTheme.ink)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }
}

private struct LioArrivalDecisionCard: View {
    let language: LioLanguage
    let rules: LioArrivalRules
    let decision: LioArrivalDecision

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Label(headline, systemImage: symbol)
                .font(.headline)
                .foregroundStyle(tint)
                .accessibilityIdentifier("lio.arrival.decision")
            ForEach(details, id: \.self) { line in
                Text(line).font(.subheadline).fixedSize(horizontal: false, vertical: true)
            }
            Text(language.text("Rules change. The official notice always wins.", "政策会调整，一切以官方为准。"))
                .font(.footnote.weight(.semibold))
            LioArrivalSources(language: language, sources: decision.sources, checkedAt: decision.checkedAt)
        }
        .foregroundStyle(LioTheme.ink)
        .padding(LioTheme.Spacing.md)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private var symbol: String {
        switch decision.outcome {
        case .visaFree, .transit: "checkmark.seal"
        case .visaRequired: "doc.text"
        case .checkOfficial: "exclamationmark.triangle"
        }
    }

    private var tint: Color {
        switch decision.outcome {
        case .visaFree, .transit: LioTheme.jade
        case .visaRequired, .checkOfficial: LioTheme.vermilion
        }
    }

    private var headline: String {
        switch decision.outcome {
        case .visaFree(let policy):
            language.text("Visa-free entry, up to \(policy.maxStayDays) days", "可免签入境，最多停留 \(policy.maxStayDays) 天")
        case .transit(let policy):
            language.text("Visa-free transit, up to \(policy.maxStayDays) days", "可过境免签，最多停留 \(policy.maxStayDays) 天")
        case .visaRequired:
            language.text("Get a visa before you travel", "需要提前办理签证")
        case .checkOfficial:
            language.text("Check the official sources", "请以官方为准")
        }
    }

    private var details: [String] {
        switch decision.outcome {
        case .visaFree(let policy), .transit(let policy):
            var lines = [policy.summary.text(language), policy.notCovered.text(language)]
            if let until = policy.validUntil {
                lines.append(language.text("This policy is published until \(until), 24:00 Beijing time.",
                                           "该政策公布的截止时间为 \(until) 北京时间 24 时。"))
            }
            return lines
        case .visaRequired:
            return [language.text("Your trip is outside the visa-free rules in the official notices we checked.",
                                  "按我们核对过的官方通知，你的行程不在免签范围内。")]
        case .checkOfficial(let reason):
            return [reasonText(reason)]
        }
    }

    private func reasonText(_ reason: LioArrivalDecision.Reason) -> String {
        switch reason {
        case .notCovered:
            language.text("We have not checked the rules for this passport yet.", "这个国籍的规则我们还没有核对。")
        case .notVerified:
            language.text("We have not yet confirmed an official notice for visa-free entry with this passport. Visa-free transit may apply if you fly on to a third country.",
                          "我们还没有核对到这个国籍直接免签的官方通知。如果离境后前往第三国（地区），可能适用过境免签。")
        case .policyEnded:
            language.text("The published end date of the visa-free policy is before your arrival.",
                          "免签政策公布的截止日期早于你的入境日期。")
        case .policyMayEndDuringTrip:
            language.text("Your trip runs past the published end date of the visa-free policy.",
                          "你的行程跨过了免签政策公布的截止日期。")
        case .overdueForReview:
            language.text("These rules are due for a recheck, so we are not giving an answer from them.",
                          "这些规则已过核对期，暂不据此给出结论。")
        }
    }
}

private struct LioArrivalSources: View {
    let language: LioLanguage
    let sources: [LioArrivalSource]
    let checkedAt: LioArrivalDay

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text(language.text("Official sources · checked \(checkedAt)", "官方来源 · 核对于 \(checkedAt)"))
                .font(.footnote.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary)
            ForEach(sources, id: \.url) { source in
                if LioArrivalRules.isOfficial(source.url) {
                    Link(destination: source.url) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(source.publisher.text(language)).font(.footnote)
                            Text([source.url.host, source.published.map(\.description)].compactMap { $0 }
                                .joined(separator: " · "))
                                .font(.caption).foregroundStyle(LioTheme.inkSecondary)
                        }
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .multilineTextAlignment(.leading)
                        .contentShape(Rectangle())
                    }
                    .foregroundStyle(LioTheme.vermilion)
                }
            }
        }
        .accessibilityIdentifier("lio.arrival.sources")
    }
}

// MARK: - Step 3: getting online (guidance only)

private struct LioArrivalInternetView: View {
    let language: LioLanguage

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
                ForEach(LioArrivalInternetOption.allCases) { option in
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        Label(option.title(language), systemImage: option.symbol).font(.headline)
                        Text(option.detail(language)).font(.subheadline).fixedSize(horizontal: false, vertical: true)
                    }
                    .foregroundStyle(LioTheme.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(LioTheme.Spacing.md)
                    .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                Text(LioArrivalInternetOption.footnote(language))
                    .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(LioArrivalStep.internet.title(language))
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - Step 4: taxi to the hotel

private struct LioArrivalTaxiView: View {
    let language: LioLanguage
    let tripHotel: LioArrivalHotel?
    @Environment(\.lioTaxiEntry) private var taxiEntry
    @State private var typedName = ""
    @State private var typedAddress = ""
    @State private var showingDriverCard = false

    private var hotel: LioArrivalHotel? { tripHotel ?? LioArrivalHotel(typedName: typedName, address: typedAddress) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                    if let tripHotel {
                        Text(language.text("From your trip", "来自你的行程")).font(.footnote)
                            .foregroundStyle(LioTheme.inkSecondary)
                        Text(tripHotel.nameZH).font(.title3.weight(.semibold))
                        if let address = tripHotel.addressZH { Text(address).font(.subheadline) }
                    } else {
                        Text(language.text("No hotel address in your trip yet. Type it in Chinese if you have it.",
                                           "行程里还没有酒店地址。有中文名称和地址的话，可以填在这里。"))
                            .font(.subheadline).fixedSize(horizontal: false, vertical: true)
                        TextField(language.text("Hotel name in Chinese", "酒店中文名"), text: $typedName)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("lio.arrival.hotel.name")
                        TextField(language.text("Address in Chinese (optional)", "中文地址（可不填）"), text: $typedAddress,
                                  axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityIdentifier("lio.arrival.hotel.address")
                    }
                }
                .foregroundStyle(LioTheme.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(LioTheme.Spacing.md)
                .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))

                Button { showingDriverCard = true } label: {
                    Label(language.text("Show the driver", "给司机看"), systemImage: "text.viewfinder")
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(.borderedProminent)
                .disabled(hotel == nil)
                .accessibilityIdentifier("lio.arrival.driver")

                if let taxiEntry {
                    NavigationLink {
                        LioTaxiView(language: language, service: taxiEntry.service, tripPlaces: taxiEntry.tripPlaces,
                                    recentStore: taxiEntry.recentStore)
                    } label: {
                        Label(language.text("Find it and open DiDi", "搜地点，用滴滴打车"), systemImage: "car.fill")
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("lio.arrival.taxi")
                }
            }
            .padding(18)
        }
        .background(LioTheme.paper)
        .navigationTitle(LioArrivalStep.taxi.title(language))
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showingDriverCard) {
            if let hotel {
                LioDriverSign(language: language, nameZH: hotel.nameZH, nameEN: hotel.nameEN, addressZH: hotel.addressZH,
                              requestZH: hotel.driverRequestZH, identifierPrefix: "lio.arrival.driver")
            }
        }
    }
}

#if DEBUG
struct LioArrivalShotTaxi: View { let language: LioLanguage; var body: some View { LioArrivalTaxiView(language: language, tripHotel: LioArrivalHotel(hotels: LioArrivalPreview.hotels)) } }
enum LioArrivalPreview {
    static var requested: Bool { ProcessInfo.processInfo.arguments.contains("--lio-arrival-preview") }

    /// A made-up stay for previews only.
    static let hotels: [LioRichItinerary.Hotel] = [
        .init(id: "preview", place: .init(nameZH: "示例大酒店", nameEN: "Example Grand Hotel", address: "示例区示例路 8 号",
                                          matched: true, point: nil), note: nil),
    ]
}

#Preview("Checklist") {
    NavigationStack { LioArrivalView(language: .chinese, hotels: LioArrivalPreview.hotels) }
}

#Preview("Entry") {
    NavigationStack { LioArrivalEntryView(language: .english, rules: try? LioArrivalRules.bundled(), arrival: .now) }
}
#endif
#endif
