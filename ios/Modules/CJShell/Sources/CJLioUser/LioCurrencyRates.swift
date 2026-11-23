import Foundation

struct LioCurrencyRates: Decodable {
    enum Currency: String, CaseIterable {
        case cny = "CNY"
        case usd = "USD"
        case eur = "EUR"
        case gbp = "GBP"
        case jpy = "JPY"
        case krw = "KRW"
        case aud = "AUD"
        case cad = "CAD"

        var fractionDigits: Int {
            switch self {
            case .jpy, .krw: 0
            default: 2
            }
        }
    }

    let source: String
    let date: String
    private let rates: [Currency: Decimal]

    private enum CodingKeys: String, CodingKey {
        case version, source, base, date, rates
    }

    init(from decoder: any Decoder) throws {
        let data = try decoder.container(keyedBy: CodingKeys.self)
        let version = try data.decode(String.self, forKey: .version)
        let base = try data.decode(String.self, forKey: .base)
        let source = try data.decode(String.self, forKey: .source)
        let date = try data.decode(String.self, forKey: .date)
        let rawRates = try data.decode([String: String].self, forKey: .rates)
        let calendar = ISO8601DateFormatter()
        calendar.formatOptions = .withFullDate
        guard version == "CURRENCY.1", base == "EUR", source == "ECB",
              let day = calendar.date(from: date), calendar.string(from: day) == date
        else {
            throw DecodingError.dataCorruptedError(forKey: .version, in: data, debugDescription: "Invalid rate snapshot")
        }

        var rates: [Currency: Decimal] = [.eur: 1]
        for (code, raw) in rawRates {
            guard let currency = Currency(rawValue: code) else { continue }
            guard raw.range(of: #"^[0-9]+(\.[0-9]+)?$"#, options: .regularExpression) != nil,
                  let value = Decimal(string: raw, locale: Locale(identifier: "en_US_POSIX")),
                  value > 0, currency != .eur || value == 1
            else {
                throw DecodingError.dataCorruptedError(forKey: .rates, in: data, debugDescription: "Invalid exchange rate")
            }
            rates[currency] = value
        }
        guard rates[.cny] != nil else {
            throw DecodingError.dataCorruptedError(forKey: .rates, in: data, debugDescription: "Missing CNY rate")
        }
        self.source = source
        self.date = date
        self.rates = rates
    }

    var currencies: [Currency] { Currency.allCases.filter { rates[$0] != nil } }

    func convert(_ amount: Decimal, from origin: Currency, to destination: Currency) -> Decimal? {
        guard !amount.isNaN, amount >= 0,
              let originRate = rates[origin], let destinationRate = rates[destination] else { return nil }
        var unrounded = amount / originRate * destinationRate
        guard !unrounded.isNaN else { return nil }
        var rounded = Decimal()
        NSDecimalRound(&rounded, &unrounded, destination.fractionDigits, .plain)
        return rounded
    }
}

#if DEBUG
extension LioCurrencyRates {
    static func fixture() async throws -> LioCurrencyRates {
        try JSONDecoder().decode(Self.self, from: Data("""
        {"version":"CURRENCY.1","source":"ECB","base":"EUR","date":"2026-11-20",
        "rates":{"CNY":"8","USD":"1.25","GBP":"0.85","JPY":"160","KRW":"1400","AUD":"1.65","CAD":"1.50"}}
        """.utf8))
    }
}
#endif
