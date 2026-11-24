import Foundation
import Testing
@testable import CJLioUser

struct LioCurrencyRatesTests {
    @Test func convertsUsingBothRatesBeforeRounding() throws {
        let rates = try decode()
        #expect(rates.convert(100, from: .cny, to: .usd) == Decimal(string: "15.63"))
        #expect(rates.convert(100, from: .usd, to: .cny) == 640)
        #expect(rates.convert(Decimal(string: "0.125")!, from: .eur, to: .jpy) == 20)
        #expect(rates.convert(100, from: .cny, to: .gbp) == nil)
        #expect(rates.convert(-1, from: .cny, to: .usd) == nil)
        #expect(rates.date == "2026-11-20")
        #expect(rates.currencies == [.cny, .usd, .eur, .jpy])
    }

    @Test(arguments: ["0", "-1", "1x", "1e2", "NaN"])
    func rejectsInvalidRates(_ rate: String) {
        #expect(throws: DecodingError.self) { try decode(rate: rate) }
    }

    @Test func rejectsInvalidDate() {
        #expect(throws: DecodingError.self) { try decode(date: "2026-02-30") }
    }

    private func decode(rate: String = "1.25", date: String = "2026-11-20") throws -> LioCurrencyRates {
        try JSONDecoder().decode(LioCurrencyRates.self, from: Data("""
        {"version":"CURRENCY.1","source":"ECB","base":"EUR","date":"\(date)",
        "rates":{"CNY":"8","USD":"\(rate)","JPY":"160","CHF":"0.9"}}
        """.utf8))
    }
}
