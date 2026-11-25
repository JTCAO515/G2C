import Foundation

/// Static bilingual pages at the back of every roadbook. Emergency numbers and phrases come from the
/// app's existing directories (Local Support, Phrase Cards) so there is one source for each; payment and
/// internet notes are general reminders with no prices and no live information.
struct LioRoadbookEssentialItem: Identifiable, Sendable {
    let id: String
    let title: String
    let detail: String?
    /// A mainland number to dial, when the item is a phone line.
    let phone: String?
    /// Chinese to show someone, when the reader is using English.
    let chinese: String?

    init(id: String, title: String, detail: String? = nil, phone: String? = nil, chinese: String? = nil) {
        self.id = id
        self.title = title
        self.detail = detail
        self.phone = phone
        self.chinese = chinese
    }
}

struct LioRoadbookEssentialSection: Identifiable, Sendable {
    let id: String
    let title: String
    let symbol: String
    let items: [LioRoadbookEssentialItem]
}

enum LioRoadbookEssentials {
    static let phraseCategories: [LioPhraseCategory] = [.taxi, .directions, .dining, .healthcare]

    static func sections(_ language: LioLanguage) -> [LioRoadbookEssentialSection] {
        [emergency(language), phrases(language), payment(language), internet(language)]
    }

    private static func emergency(_ language: LioLanguage) -> LioRoadbookEssentialSection {
        let lines = (LocalSupportDirectory.emergencyContacts + LocalSupportDirectory.helpContacts).map { contact in
            LioRoadbookEssentialItem(id: contact.id, title: contact.title.localized(language),
                                     detail: contact.detail?.localized(language), phone: contact.phone.number)
        }
        let embassy = LioRoadbookEssentialItem(
            id: "embassy", title: language.text("Your embassy or consulate", "使领馆"),
            detail: language.text("Find the phone number and address for your country in Tools → Local Support.",
                                  "在「工具 → 本地协助」按国籍查看电话和地址。"))
        let medical = LioRoadbookEssentialItem(
            id: "medical", title: language.text("Medical card", "医疗卡"),
            detail: language.text("Keep allergies and medicines in Local Support. It stays on this phone and is not added to this PDF.",
                                  "过敏和用药写在「本地协助」的医疗卡里，只存在本机，不放进路书 PDF。"))
        return .init(id: "emergency", title: language.text("Emergency", "紧急信息"), symbol: "sos",
                     items: lines + [embassy, medical])
    }

    private static func phrases(_ language: LioLanguage) -> LioRoadbookEssentialSection {
        let items = phraseCategories.flatMap { category in
            category.phrases.prefix(2).map { phrase in
                LioRoadbookEssentialItem(id: phrase.id, title: phrase.text(in: language),
                                         detail: category.title(in: language), chinese: phrase.chinese)
            }
        }
        return .init(id: "phrases", title: language.text("Useful phrases", "常用短语"), symbol: "text.bubble", items: items)
    }

    private static func payment(_ language: LioLanguage) -> LioRoadbookEssentialSection {
        .init(id: "payment", title: language.text("Paying", "支付"), symbol: "wallet.pass", items: [
            .init(id: "payment-apps",
                  title: language.text("Set up Alipay or Weixin Pay before you go", "出发前开通支付宝或微信支付"),
                  detail: language.text("Most shops, taxis and metro stations take them. Link your international card in the official app; Tools → Payment Setup Guide has the steps.",
                                        "大多数商店、出租车和地铁都能用。在官方 App 里绑定境外银行卡，步骤见「工具 → 支付开通指南」。")),
            .init(id: "payment-backup",
                  title: language.text("Keep a backup", "准备备用方式"),
                  detail: language.text("Carry some cash and a second card in case a payment does not go through.",
                                        "带少量现金和第二张卡，以防支付不成功。")),
            .init(id: "payment-official",
                  title: language.text("Limits and fees", "限额与手续费"),
                  detail: language.text("Limits and fees for foreign cards change; check them in the payment app.",
                                        "境外卡的限额和手续费会调整，以支付 App 内说明为准。")),
        ])
    }

    private static func internet(_ language: LioLanguage) -> LioRoadbookEssentialSection {
        .init(id: "internet", title: language.text("Getting online", "上网"), symbol: "antenna.radiowaves.left.and.right", items: [
            .init(id: "internet-data",
                  title: language.text("Arrange mobile data before you land", "落地前准备好流量"),
                  detail: language.text("Use international roaming or a travel eSIM, or buy a local SIM with your passport.",
                                        "开通国际漫游或旅行 eSIM，或凭护照购买本地电话卡。")),
            .init(id: "internet-apps",
                  title: language.text("Some overseas apps may not load", "部分境外应用可能无法使用"),
                  detail: language.text("Download maps, tickets and this roadbook while you still have a connection.",
                                        "趁有网络时提前下载地图、票据和这本路书。")),
            .init(id: "internet-wifi",
                  title: language.text("Public Wi-Fi", "公共 Wi-Fi"),
                  detail: language.text("Hotels usually have Wi-Fi; some public networks need a Chinese phone number for a text code.",
                                        "酒店一般有 Wi-Fi；部分公共网络需要中国手机号接收验证码。")),
        ])
    }
}
