#if os(iOS)
import SwiftUI

/// The one question a step of going to China asks when the traveller taps "Go" (#1979), on a sheet of its own so the
/// page itself carries no form. The passport question is `LioTripNationalityPicker` with the step's question as its
/// title. Answers stay on this phone, in the trip home's own file.

/// The "arrival" step: which day you land, and by which flight or train. The day is the answer the step needs; the
/// number is optional.
struct LioTripArrivalAsk: View {
    let language: LioLanguage
    let save: (LioTripDay, String?) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var day: Date
    @State private var number: String

    init(language: LioLanguage, profile: LioTripProfile?, save: @escaping (LioTripDay, String?) -> Void) {
        self.language = language
        self.save = save
        // Nothing is saved until the traveller taps Save, so a suggested day (two weeks out) is only a starting point.
        _day = State(initialValue: (profile?.arrival ?? LioTripDay(date: .now).adding(days: 14)).start())
        _number = State(initialValue: profile?.arrivalNumber ?? "")
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: LioTheme.Spacing.xs) {
                        DatePicker(language.text("Arrival day", "到达日期"), selection: $day, displayedComponents: .date)
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("lio.trip-home.ask.arrival.day")
                        TextField(language.text("Flight or train number (optional)", "航班号或车次（选填）"), text: $number)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .submitLabel(.done)
                            .frame(minHeight: 44)
                            .accessibilityIdentifier("lio.trip-home.ask.arrival.number")
                    }
                    .padding(LioTheme.Spacing.md)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .lioCard(RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                }
                .padding(LioTheme.Spacing.md)
            }
            .background(LioTheme.paper)
            .safeAreaInset(edge: .bottom) {
                Button {
                    save(LioTripDay(date: day), LioTripProfile.cleanArrivalNumber(number))
                    dismiss()
                } label: {
                    Text(language.text("Save", "保存"))
                }
                .buttonStyle(LioPrimaryButtonStyle())
                .padding(LioTheme.Spacing.md)
                .background(LioTheme.paper)
                .accessibilityIdentifier("lio.trip-home.ask.arrival.save")
            }
            .navigationTitle(language.text("When do you arrive?", "哪天到中国？"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Cancel", "取消")) { dismiss() }
                }
            }
        }
        .tint(LioTheme.vermilion)
    }
}

/// The "stay" step: the hotel level, or any. It continues to the hotel search.
struct LioTripStayAsk: View {
    let language: LioLanguage
    let save: (Int?) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var stars: Int?

    init(language: LioLanguage, stars: Int?, save: @escaping (Int?) -> Void) {
        self.language = language
        self.save = save
        _stars = State(initialValue: stars)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    Picker(language.text("Hotel level", "酒店星级"), selection: $stars) {
                        Text(language.text("Any", "不限")).tag(Int?.none)
                        ForEach(Array(LioTripProfile.starLevels), id: \.self) { level in
                            Text(language.text("\(level) stars", "\(level) 星")).tag(Int?.some(level))
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("lio.trip-home.ask.stay.stars")
                }
                .padding(LioTheme.Spacing.md)
            }
            .background(LioTheme.paper)
            .safeAreaInset(edge: .bottom) {
                Button {
                    save(stars)
                    dismiss()
                } label: {
                    Text(language.text("Continue", "继续"))
                }
                .buttonStyle(LioPrimaryButtonStyle())
                .padding(LioTheme.Spacing.md)
                .background(LioTheme.paper)
                .accessibilityIdentifier("lio.trip-home.ask.stay.continue")
            }
            .navigationTitle(language.text("What hotel level?", "想住几星的酒店？"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Cancel", "取消")) { dismiss() }
                }
            }
        }
        .tint(LioTheme.vermilion)
    }
}
#endif
