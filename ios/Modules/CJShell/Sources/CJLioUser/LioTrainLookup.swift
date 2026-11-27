import Foundation

/// Train-number lookup (#2007). There is no data source we may use for stops and times by train number
/// (C7 research, 2026-11-27: 12306 allows copying its data only with written permission, and the paid APIs
/// need a signed contract), so the page checks the number, then sends the traveller to 12306's own pages.
/// Nothing is sent to us or to anyone else from here.
enum LioTrainLookup {
    enum Problem: Error, Equatable, Sendable {
        case empty, badNumber

        func message(_ language: LioLanguage) -> String {
            switch self {
            case .empty:
                language.text("Enter a train number, for example G1 or D3125.", "请输入车次，例如 G1 或 D3125。")
            case .badNumber:
                language.text("That doesn't look like a train number. Use the letter and digits on your ticket, like G1.",
                              "这不像车次。请输入车票上的字母和数字，例如 G1。")
            }
        }
    }

    /// Optional class letter (G, D, C, Z, T, K, Y, L, S, P, A) then 1–4 digits; some trains are all digits.
    static let pattern = #"^[GDCZTKYLSPA]?[0-9]{1,4}$"#

    static func normalize(_ text: String) -> String {
        let folded = text.applyingTransform(.fullwidthToHalfwidth, reverse: false) ?? text
        return folded.uppercased().filter { !$0.isWhitespace && $0 != "-" }
    }

    static func check(_ text: String) -> Result<String, Problem> {
        let number = normalize(text)
        guard !number.isEmpty else { return .failure(.empty) }
        guard number.range(of: pattern, options: .regularExpression) != nil else { return .failure(.badNumber) }
        return .success(number)
    }

    /// 12306's mobile page that looks a train up by number and date (the page can't be pre-filled, so the
    /// number is shown and can be copied before opening it), and its English passenger entry.
    static let byNumberURL = URL(string: "https://mobile.12306.cn/weixin/wxcore/initCC")!
    static let englishURL = URL(string: "https://www.12306.cn/en/index.html")!

    static func reason(_ language: LioLanguage) -> String {
        language.text(
            "Stops and times by train number come from 12306. We don't have a data source we're allowed to use for them, so we send you to 12306's own page rather than show numbers we can't vouch for.",
            "按车次查经停站和时刻，权威来源是 12306。我们暂时没有可合规使用的数据来源，所以带你去 12306 官方页自己查，不展示我们无法保证的数字。")
    }
}
