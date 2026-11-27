import Foundation

/// Presentation helpers for the currency converter: flags, names, quick amounts and the
/// two-way amount linking. Kept free of SwiftUI so the rules are unit-testable.
extension LioCurrencyRates.Currency {
    /// Flag shown beside the three-letter code. EUR uses the EU flag.
    var flag: String {
        switch self {
        case .cny: "🇨🇳"
        case .usd: "🇺🇸"
        case .eur: "🇪🇺"
        case .gbp: "🇬🇧"
        case .jpy: "🇯🇵"
        case .krw: "🇰🇷"
        case .aud: "🇦🇺"
        case .cad: "🇨🇦"
        }
    }

    func name(_ language: LioLanguage) -> String {
        switch self {
        case .cny: language.text("Chinese yuan", "人民币")
        case .usd: language.text("US dollar", "美元")
        case .eur: language.text("Euro", "欧元")
        case .gbp: language.text("British pound", "英镑")
        case .jpy: language.text("Japanese yen", "日元")
        case .krw: language.text("South Korean won", "韩元")
        case .aud: language.text("Australian dollar", "澳元")
        case .cad: language.text("Canadian dollar", "加元")
        }
    }

    /// One-tap amounts for the top field, sized to what a traveller typically handles in that currency.
    var quickAmounts: [Decimal] {
        switch self {
        case .cny: [50, 100, 200, 500, 1_000]
        case .jpy: [1_000, 5_000, 10_000, 20_000, 50_000]
        case .krw: [10_000, 50_000, 100_000, 500_000, 1_000_000]
        case .usd, .eur, .gbp, .aud, .cad: [10, 20, 50, 100, 500]
        }
    }
}

enum LioCurrencyField: Equatable {
    case origin
    case destination
}

/// Which field the traveller last typed in, and what they typed. The other field is derived.
struct LioCurrencyEntry: Equatable {
    var active: LioCurrencyField = .origin
    var text = "100"

    /// Parses what the traveller typed. Grouping separators (from a derived value that was tapped
    /// into) are ignored; anything else that isn't a plain number is rejected.
    static func parse(_ text: String, locale: Locale) -> Decimal? {
        var cleaned = text.trimmingCharacters(in: .whitespaces)
        if let grouping = locale.groupingSeparator, !grouping.isEmpty, grouping != locale.decimalSeparator {
            cleaned = cleaned.replacingOccurrences(of: grouping, with: "")
        }
        guard !cleaned.isEmpty else { return nil }
        return try? Decimal(cleaned, format: .number.locale(locale))
    }

    /// Text for the field that is not being typed in, or `nil` when the entry can't be converted.
    func derivedText(rates: LioCurrencyRates, origin: LioCurrencyRates.Currency,
                     destination: LioCurrencyRates.Currency, locale: Locale) -> String? {
        guard let number = Self.parse(text, locale: locale) else { return nil }
        let source = active == .origin ? origin : destination
        let target = active == .origin ? destination : origin
        guard let converted = rates.convert(number, from: source, to: target) else { return nil }
        return converted.formatted(.number.grouping(.never).precision(.fractionLength(target.fractionDigits)).locale(locale))
    }

    /// Plain (ungrouped) text for a quick amount.
    static func text(for amount: Decimal, locale: Locale) -> String {
        amount.formatted(.number.grouping(.never).locale(locale))
    }
}
