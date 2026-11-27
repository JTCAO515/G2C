import Foundation
import Testing
@testable import CJLioUser

struct LioCurrencyConverterTests {
    private let locale = Locale(identifier: "en_US")

    @Test func everyCurrencyHasFlagNamesAndQuickAmounts() {
        for currency in LioCurrencyRates.Currency.allCases {
            #expect(!currency.flag.isEmpty)
            #expect(!currency.name(.english).isEmpty)
            #expect(!currency.name(.chinese).isEmpty)
            #expect(currency.quickAmounts.count == 5)
            #expect(currency.quickAmounts == currency.quickAmounts.sorted())
        }
        #expect(LioCurrencyRates.Currency.cny.flag == "🇨🇳")
    }

    @Test func parsesPlainAndGroupedAmounts() {
        #expect(LioCurrencyEntry.parse("100", locale: locale) == 100)
        #expect(LioCurrencyEntry.parse("1,563.5", locale: locale) == Decimal(string: "1563.5"))
        #expect(LioCurrencyEntry.parse("", locale: locale) == nil)
        #expect(LioCurrencyEntry.parse("abc", locale: locale) == nil)
    }

    @Test func derivedFieldFollowsTheActiveOne() throws {
        let rates = try fixture()
        var entry = LioCurrencyEntry(active: .origin, text: "100")
        #expect(entry.derivedText(rates: rates, origin: .cny, destination: .usd, locale: locale) == "15.63")
        // Typing in the lower field converts back to the upper currency.
        entry = LioCurrencyEntry(active: .destination, text: "15.63")
        #expect(entry.derivedText(rates: rates, origin: .cny, destination: .usd, locale: locale) == "100.03")
        entry = LioCurrencyEntry(active: .origin, text: "x")
        #expect(entry.derivedText(rates: rates, origin: .cny, destination: .usd, locale: locale) == nil)
    }

    @Test func quickAmountTextHasNoGrouping() {
        #expect(LioCurrencyEntry.text(for: 1_000_000, locale: locale) == "1000000")
    }

    @Test func unitRateIsUnrounded() throws {
        let rates = try fixture()
        #expect(rates.unitRate(from: .cny, to: .usd) == Decimal(string: "0.15625"))
        #expect(rates.unitRate(from: .cny, to: .gbp) == nil)
    }

    private func fixture() throws -> LioCurrencyRates {
        try JSONDecoder().decode(LioCurrencyRates.self, from: Data("""
        {"version":"CURRENCY.1","source":"ECB","base":"EUR","date":"2026-11-20",
        "rates":{"CNY":"8","USD":"1.25","JPY":"160"}}
        """.utf8))
    }
}
