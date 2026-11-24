import Foundation

/// English names and price text for DiDi ride options (#1451). The Chinese name stays the provider's own.
enum LioTaxiFareText {
    /// Generic English name for a ride option this table does not know yet; the Chinese name is shown beside it.
    static let otherRide = "Other ride option"

    private static let byCategory: [String: String] = [
        "1": "Express",
        "201": "Discount Express",
        "8": "Premier",
    ]

    /// Known DiDi product names. Longer names come first so "六座专车" is not read as "专车".
    private static let byName: [(String, String)] = [
        ("惊喜特价", "Surprise Deal"),
        ("特惠快车", "Discount Express"),
        ("特快", "Express Plus"),
        ("极速拼车", "Express Carpool"),
        ("拼车", "Carpool"),
        ("滴滴轻享", "DiDi Lite"),
        ("轻享", "DiDi Lite"),
        ("六座专车", "6-Seat Premier"),
        ("六座商务", "6-Seat Business"),
        ("商务车", "Business Van"),
        ("豪华车", "Luxe"),
        ("礼橙专车", "Premier"),
        ("专车", "Premier"),
        ("优享", "Comfort"),
        ("舒适型", "Comfort"),
        ("出租车", "Taxi"),
        ("快车", "Express"),
    ]

    static func englishName(category: String, chinese: String) -> String {
        if let name = byCategory[category] { return name }
        let trimmed = chinese.trimmingCharacters(in: .whitespacesAndNewlines)
        if let match = byName.first(where: { trimmed.contains($0.0) }) { return match.1 }
        // Already English from the provider.
        if !trimmed.isEmpty, trimmed.unicodeScalars.allSatisfy(\.isASCII) { return trimmed }
        return otherRide
    }

    /// "¥30–42" from the minor-unit range when the provider gives one; otherwise the provider's text,
    /// with "¥" added when it is a bare CNY number.
    static func price(display: String, currency: String, minMinor: Int?, maxMinor: Int?) -> String {
        if currency == "CNY", let minMinor, let maxMinor, minMinor > 0, maxMinor >= minMinor {
            let low = yuan(minMinor), high = yuan(maxMinor)
            return low == high ? "¥\(low)" : "¥\(low)–\(high)"
        }
        // "31-36" reads as a range: use the same dash as the formatted ranges.
        let text = display.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: #"(?<=\d)\s*[-~～]\s*(?=\d)"#, with: "–", options: .regularExpression)
        let hasSymbol = text.contains("¥") || text.contains("￥") || text.contains("元") || text.contains("CNY")
        if currency == "CNY", !hasSymbol, text.first?.isNumber == true { return "¥" + text }
        return text
    }

    private static func yuan(_ minor: Int) -> String {
        minor % 100 == 0 ? String(minor / 100) : String(format: "%.1f", Double(minor) / 100)
            .replacingOccurrences(of: ".0", with: "")
    }
}
