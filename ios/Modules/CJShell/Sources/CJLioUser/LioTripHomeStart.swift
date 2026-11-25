#if os(iOS)
import SwiftUI

/// The Trips tab with no trip yet: plan with Lio in the chat, or just get ready with three questions.
struct LioTripHomeStart: View {
    let language: LioLanguage
    let openChat: () -> Void
    let getReady: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.lg) {
            Text(language.text("Trips", "行程"))
                .font(LioTheme.display(.largeTitle).bold())
                .foregroundStyle(LioTheme.ink)
                .accessibilityAddTraits(.isHeader)
            HStack(alignment: .center, spacing: LioTheme.Spacing.sm) {
                LioPortrait(size: 56).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    Text(language.text("Heading to China?", "准备去中国？"))
                        .font(LioTheme.display(.title2).weight(.semibold))
                        .foregroundStyle(LioTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(language.text("See what to sort out before you go, or let Lio plan your days.",
                                       "先看看出发前要办哪些事，或请 Lio 排好每天去哪。"))
                        .font(.subheadline)
                        .foregroundStyle(LioTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .combine)
            // JT 2026-11-25: "Just get ready" first; planning needs a chat round first.
            entry(symbol: "checklist", title: language.text("Just get ready", "先只做准备"),
                  detail: language.text("Three questions, then a checklist: entry, payment, data, hotel, bookings.",
                                        "回答三个问题，得到准备清单：入境、支付、上网、酒店、预约。"),
                  identifier: "lio.trip-home.start.ready", action: getReady)
            entry(symbol: "bubble.left.and.text.bubble.right", title: language.text("Plan with Lio", "帮我规划"),
                  detail: language.text("Tell Lio your city, days and interests; it plans each day.",
                                        "告诉 Lio 城市、天数和喜好，排好每天的行程。"),
                  identifier: "lio.trip-home.start.plan", action: openChat)
            Text(language.text("Trips you saved before are under All trips.", "以前保存的行程在右上角「所有行程」里。"))
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityIdentifier("lio.trip-home.start")
    }

    private func entry(symbol: String, title: String, detail: String, identifier: String,
                       action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: LioTheme.Spacing.sm) {
                Image(systemName: symbol)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(LioTheme.vermilion)
                    .frame(width: 40, height: 40)
                    .background(LioTheme.surfaceSunken, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    Text(title).font(.headline).foregroundStyle(LioTheme.ink)
                    Text(detail).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityHidden(true)
            }
            .padding(LioTheme.Spacing.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            .contentShape(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier(identifier)
    }
}

/// "Just get ready": when you arrive and for how long, which passport, which city first. Every answer can be
/// skipped; skipping all of them gives the general checklist. Answers stay on this phone.
struct LioTripHomeStartSheet: View {
    static let defaultStayDays = 7
    static let maximumStayDays = 90

    let language: LioLanguage
    let initial: LioTripProfile?
    @Binding var nationality: String
    let save: (LioTripProfile) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var datesSet: Bool
    @State private var arrival: Date
    @State private var stayDays: Int
    @State private var cityID: String?
    @State private var passport: String

    init(language: LioLanguage, initial: LioTripProfile?, nationality: Binding<String>,
         save: @escaping (LioTripProfile) -> Void) {
        self.language = language
        self.initial = initial
        _nationality = nationality
        self.save = save
        let defaultArrival = LioTripDay(date: .now).adding(days: 14)
        // A new trip starts with no dates, so nothing the traveller did not pick is saved (#1665 review P3-2).
        _datesSet = State(initialValue: initial?.arrival != nil)
        _arrival = State(initialValue: (initial?.arrival ?? defaultArrival).start())
        _stayDays = State(initialValue: initial?.stayDays ?? Self.defaultStayDays)
        _cityID = State(initialValue: initial?.cityID)
        _passport = State(initialValue: nationality.wrappedValue)
    }

    private var editing: Bool { initial != nil }

    private func profile(skipping: Bool) -> LioTripProfile {
        let started = initial?.startedAt ?? .now
        guard !skipping else {
            return LioTripProfile(arrival: nil, stayDays: nil, cityID: nil, startedAt: started)
        }
        return LioTripProfile(arrival: datesSet ? LioTripDay(date: arrival) : nil, stayDays: datesSet ? stayDays : nil,
                              cityID: cityID, planID: initial?.planID,
                              onwardToThirdCountry: initial?.onwardToThirdCountry, startedAt: started)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    if !editing {
                        Text(language.text("Answer what you know; you can change it later.", "知道多少答多少，以后还能改。"))
                            .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                    }
                    question(1, language.text("When do you arrive in China?", "哪天到中国？")) {
                        Toggle(language.text("Dates not decided yet", "还没定日期"), isOn: Binding(get: { !datesSet }, set: { datesSet = !$0 }))
                            .tint(LioTheme.vermilion)
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("lio.trip-home.form.no-dates")
                        if datesSet {
                            DatePicker(language.text("Arrival day", "到达日期"), selection: $arrival, displayedComponents: .date)
                                .frame(minHeight: 44)
                                .accessibilityIdentifier("lio.trip-home.form.arrival")
                            Stepper(value: $stayDays, in: 1...Self.maximumStayDays) {
                                Text(language.text("Staying \(stayDays) \(stayDays == 1 ? "day" : "days")", "待 \(stayDays) 天"))
                            }
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("lio.trip-home.form.days")
                        }
                    }
                    question(2, language.text("Which passport do you travel on?", "用哪国护照？")) {
                        NavigationLink {
                            LioTripNationalityPicker(language: language, selection: $passport)
                        } label: {
                            choiceRow(countryName(passport) ?? language.text("Choose", "选择国籍"))
                        }
                        .accessibilityIdentifier("lio.trip-home.form.passport")
                        Text(language.text("Local Support and Arrival Mode use the same choice.", "本地协助和落地模式也用这个选择。"))
                            .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                    }
                    question(3, language.text("Which city first?", "先去哪座城市？")) {
                        NavigationLink {
                            LioTripCityPicker(language: language, selection: $cityID)
                        } label: {
                            choiceRow(cityID.flatMap(LioMetroCity.named)?.name(in: language)
                                      ?? language.text("Not decided", "还没定"))
                        }
                        .accessibilityIdentifier("lio.trip-home.form.city")
                    }
                    Label(language.text("These answers stay on this phone and are not sent anywhere.",
                                        "这些回答只存在这台手机上，不会发出去。"), systemImage: "lock")
                        .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(LioTheme.Spacing.md)
            }
            .background(LioTheme.paper)
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: LioTheme.Spacing.xs) {
                    Button {
                        if !passport.isEmpty { nationality = passport }
                        save(profile(skipping: false))
                        dismiss()
                    } label: {
                        Text(editing ? language.text("Save", "保存") : language.text("Make my checklist", "生成准备清单"))
                    }
                    .buttonStyle(LioPrimaryButtonStyle())
                    .accessibilityIdentifier("lio.trip-home.form.save")
                    if !editing {
                        Button {
                            save(profile(skipping: true))
                            dismiss()
                        } label: {
                            Text(language.text("Skip and see the general list", "跳过，先看通用清单"))
                        }
                        .buttonStyle(LioSecondaryButtonStyle())
                        .accessibilityIdentifier("lio.trip-home.form.skip")
                    }
                }
                .padding(LioTheme.Spacing.md)
                .background(LioTheme.paper)
            }
            .navigationTitle(editing ? language.text("Edit this trip", "修改这趟旅行") : language.text("Just get ready", "先只做准备"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Cancel", "取消")) { dismiss() }
                }
            }
        }
        .tint(LioTheme.vermilion)
    }

    private func question<Content: View>(_ number: Int, _ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
            Text("\(number). " + title)
                .font(.headline)
                .foregroundStyle(LioTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            content()
        }
        .padding(LioTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
    }

    private func choiceRow(_ value: String) -> some View {
        HStack {
            Text(value).foregroundStyle(LioTheme.ink)
            Spacer(minLength: LioTheme.Spacing.xs)
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold))
                .foregroundStyle(LioTheme.inkSecondary).accessibilityHidden(true)
        }
        .frame(minHeight: 44)
        .contentShape(Rectangle())
    }

    private func countryName(_ code: String) -> String? {
        guard !code.isEmpty else { return nil }
        return LioTripNationalityPicker.countries.first { $0.countryCode == code }?.country.localized(language) ?? code
    }
}

/// The countries Local Support lists embassies for, searchable in both languages.
struct LioTripNationalityPicker: View {
    static let countries: [LocalSupportDirectory.Embassy] = (try? LocalSupportDirectory.bundled().embassies) ?? []

    let language: LioLanguage
    @Binding var selection: String
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""

    private var matches: [LocalSupportDirectory.Embassy] {
        Self.countries.filter {
            search.isEmpty || $0.country.zh.localizedStandardContains(search) || $0.country.en.localizedStandardContains(search)
        }.sorted { $0.country.localized(language).localizedCompare($1.country.localized(language)) == .orderedAscending }
    }

    var body: some View {
        List {
            ForEach(matches) { country in
                Button {
                    selection = country.countryCode
                    dismiss()
                } label: {
                    HStack {
                        Text(country.country.localized(language)).foregroundStyle(LioTheme.ink)
                        Spacer()
                        if country.countryCode == selection {
                            Image(systemName: "checkmark").foregroundStyle(LioTheme.vermilion)
                        }
                    }
                    .frame(minHeight: 44)
                }
                .accessibilityAddTraits(country.countryCode == selection ? .isSelected : [])
                .accessibilityIdentifier("lio.trip-home.country." + country.countryCode)
            }
        }
        .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always),
                    prompt: language.text("Search countries", "搜索国家"))
        .navigationTitle(language.text("Passport", "护照国籍"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// The mainland cities the app has metro maps for, best known first; "Not decided" clears the choice.
struct LioTripCityPicker: View {
    let language: LioLanguage
    @Binding var selection: String?
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""

    var body: some View {
        List {
            if search.isEmpty {
                row(nil, language.text("Not decided", "还没定"))
            }
            ForEach(LioMetroCity.cities(matching: search)) { city in
                row(city.id, language == .chinese ? city.nameZH : "\(city.nameEN) · \(city.nameZH)")
            }
        }
        .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always),
                    prompt: language.text("Search cities", "搜索城市"))
        .navigationTitle(language.text("First city", "第一座城市"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func row(_ id: String?, _ title: String) -> some View {
        Button {
            selection = id
            dismiss()
        } label: {
            HStack {
                Text(title).foregroundStyle(LioTheme.ink)
                Spacer()
                if id == selection { Image(systemName: "checkmark").foregroundStyle(LioTheme.vermilion) }
            }
            .frame(minHeight: 44)
        }
        .accessibilityAddTraits(id == selection ? .isSelected : [])
        .accessibilityIdentifier("lio.trip-home.city." + (id ?? "none"))
    }
}
#endif
