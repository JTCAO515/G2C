#if os(iOS)
import SwiftUI

/// "Edit this trip" (#1979: the up-front "Just get ready" questions are gone; each step asks for what it needs when
/// the traveller taps "Go"): arrival and length of stay, passport, first city. Answers stay on this phone.
struct LioTripHomeStartSheet: View {
    static let defaultStayDays = 7
    static let maximumStayDays = 90

    let language: LioLanguage
    let initial: LioTripProfile
    @Binding var nationality: String
    /// Asks "Leisure or business?" (#1765) only while `G2CTripBusinessEnabled` is on; otherwise the form is unchanged
    /// and a purpose saved before is kept as it was.
    let offersBusiness: Bool
    let save: (LioTripProfile) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var datesSet: Bool
    @State private var arrival: Date
    @State private var stayDays: Int
    @State private var cityID: String?
    @State private var passport: String
    @State private var purpose: LioTripPurpose

    init(language: LioLanguage, initial: LioTripProfile, nationality: Binding<String>, offersBusiness: Bool = false,
         save: @escaping (LioTripProfile) -> Void) {
        self.language = language
        self.initial = initial
        _nationality = nationality
        self.offersBusiness = offersBusiness
        self.save = save
        _purpose = State(initialValue: initial.purpose ?? .leisure)
        let defaultArrival = LioTripDay(date: .now).adding(days: 14)
        // A new trip starts with no dates, so nothing the traveller did not pick is saved (#1665 review P3-2).
        _datesSet = State(initialValue: initial.arrival != nil)
        _arrival = State(initialValue: (initial.arrival ?? defaultArrival).start())
        _stayDays = State(initialValue: initial.stayDays ?? Self.defaultStayDays)
        _cityID = State(initialValue: initial.cityID)
        _passport = State(initialValue: nationality.wrappedValue)
    }

    private func profile() -> LioTripProfile {
        // What the steps asked (flight or train number, hotel level) stays as it was.
        LioTripProfile(arrival: datesSet ? LioTripDay(date: arrival) : nil, stayDays: datesSet ? stayDays : nil,
                       cityID: cityID, planID: initial.planID, onwardToThirdCountry: initial.onwardToThirdCountry,
                       purpose: offersBusiness ? purpose : initial.purpose, arrivalNumber: initial.arrivalNumber,
                       stayStars: initial.stayStars, startedAt: initial.startedAt)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
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
                    if offersBusiness {
                        question(4, language.text("What kind of trip is it?", "这趟是什么行程？")) {
                            Picker(language.text("Trip type", "行程类型"), selection: $purpose) {
                                Text(language.text("Leisure", "旅游")).tag(LioTripPurpose.leisure)
                                Text(language.text("Business", "商务")).tag(LioTripPurpose.business)
                            }
                            .pickerStyle(.segmented)
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("lio.trip-home.form.purpose")
                            Text(language.text("Business adds trade fair and meeting tasks to your checklist.",
                                               "选商务会在清单里加上参展和会面要办的事。"))
                                .font(.footnote).foregroundStyle(LioTheme.inkSecondary)
                        }
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
                        save(profile())
                        dismiss()
                    } label: {
                        Text(language.text("Save", "保存"))
                    }
                    .buttonStyle(LioPrimaryButtonStyle())
                    .accessibilityIdentifier("lio.trip-home.form.save")
                }
                .padding(LioTheme.Spacing.md)
                .background(LioTheme.paper)
            }
            .navigationTitle(language.text("Edit this trip", "修改这趟旅行"))
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
    /// The step's own question (#1979) when the picker is opened from "Go"; nil keeps the plain title.
    var question: String? = nil
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
        .navigationTitle(question ?? language.text("Passport", "护照国籍"))
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
