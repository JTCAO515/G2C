import Foundation

/// Subscription placeholder (#1452): plans and benefits shown as "coming soon" only.
/// No purchase, no StoreKit, no prices charged; JT decides real billing later.
enum LioSubscriptionPlans {
    struct Plan: Identifiable, Equatable {
        let id: String
        let nameEN: String
        let nameZH: String
        /// Monthly price in US cents, shown as text only.
        let monthlyUSCents: Int
        let highlighted: Bool

        var priceText: String { "$" + String(format: "%.2f", Double(monthlyUSCents) / 100) }
    }

    struct Benefit: Identifiable, Equatable {
        enum Value: Equatable { case included, excluded, text(en: String, zh: String) }
        let id: String
        let en: String
        let zh: String
        /// One value per plan, in `plans` order.
        let values: [Value]
    }

    static let plans: [Plan] = [
        .init(id: "explorer", nameEN: "Explorer", nameZH: "探索", monthlyUSCents: 999, highlighted: false),
        .init(id: "traveler", nameEN: "Traveler", nameZH: "畅游", monthlyUSCents: 1999, highlighted: true),
        .init(id: "concierge", nameEN: "Concierge", nameZH: "尊享", monthlyUSCents: 4999, highlighted: false),
    ]

    /// "High limit (fair use)" rather than "unlimited" (JT 2026-11-24, #1452).
    private static let highLimit = Benefit.Value.text(en: "High limit (fair use)", zh: "高额度（合理使用）")

    /// Draft benefits confirmed by JT on 2026-11-24 (#1452); the page says they are a draft.
    static let benefits: [Benefit] = [
        .init(id: "chat", en: "Chat with Lio", zh: "与 Lio 对话",
              values: [.text(en: "50 a day", zh: "每天 50 条"), highLimit, highLimit]),
        .init(id: "translate", en: "Text and voice translation", zh: "文字与语音翻译",
              values: [.included, .included, .included]),
        .init(id: "photo", en: "Photo translation", zh: "拍照翻译",
              values: [.text(en: "10 a day", zh: "每天 10 张"), .included, .included]),
        .init(id: "trips", en: "Saved trip plans", zh: "保存的行程",
              values: [.text(en: "3", zh: "3 个"), highLimit, highLimit]),
        .init(id: "tools", en: "Taxi, Nearby and Metro", zh: "打车、附近与地铁",
              values: [.included, .included, .included]),
        .init(id: "human", en: "Local help from our team", zh: "我方人员本地协助",
              values: [.excluded, .excluded, .text(en: "Planned", zh: "规划中")]),
        .init(id: "priority", en: "Priority replies", zh: "优先回复",
              values: [.excluded, .included, .included]),
    ]
}
