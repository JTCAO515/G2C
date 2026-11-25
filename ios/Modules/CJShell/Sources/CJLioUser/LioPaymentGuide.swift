import Foundation

struct LioPaymentGuideStep: Identifiable {
    /// An official page the advice comes from, shown as a link under the card.
    struct Source {
        let name: String
        let url: URL
    }

    let id: String
    let icon: String
    let title: String
    let detail: String
    var source: Source?
}

enum LioPaymentGuideProvider: String, CaseIterable, Identifiable {
    case alipay, weixin
    var id: Self { self }

    func title(in language: LioLanguage) -> String {
        switch self {
        case .alipay: language.text("Alipay", "支付宝")
        case .weixin: language.text("Weixin Pay", "微信支付")
        }
    }

    var officialInstructions: URL {
        switch self {
        case .alipay:
            URL(string: "https://english.beijing.gov.cn/latest/specials/essentialtipsfornewarrivals/paymentservices/202408/t20240830_3785647.html")!
        case .weixin:
            URL(string: "https://www.tenpayglobal.com/en/consumption/wechat/")!
        }
    }

    func steps(in language: LioLanguage) -> [LioPaymentGuideStep] {
        [
            .init(id: "register", icon: "iphone",
                  title: language.text("Set up the official app", "在官方 App 开通"),
                  detail: language.text("Install the official app and follow its sign-in or registration prompts. Choose the country code for your mobile number.",
                                        "安装官方 App，按页面提示登录或注册。填写手机号时选择正确的国家或地区区号。")),
            .init(id: "find-card", icon: "wallet.pass",
                  title: language.text("Find Bank Cards", "找到银行卡入口"),
                  detail: cardPath(in: language)),
            .init(id: "add-card", icon: "creditcard",
                  title: language.text("Add your international card", "绑定境外银行卡"),
                  detail: language.text("Use Add Card or Link a Card in the official app. Confirm your card details and follow any verification prompts from the card issuer.",
                                        "在官方 App 里选择添加或绑定银行卡，核对卡片资料并按发卡行提示完成验证。")),
            .init(id: "verify", icon: "checkmark.shield",
                  title: language.text("Finish any verification", "按提示完成验证"),
                  detail: language.text("If the app asks you to verify your identity, enter the details from the accepted document in that app. Check its confirmation before relying on the card.",
                                        "如果官方 App 要求实名，请按其提示填写支持的证件信息。看到绑卡成功提示后，再用这张卡支付。")),
        ]
    }

    static func problems(in language: LioLanguage) -> [LioPaymentGuideStep] {
        [
            .init(id: "sms", icon: "message",
                  title: language.text("Verification message missing", "收不到验证码"),
                  detail: language.text("Check the country code and phone number. If you still cannot receive the message, use the official app's help.",
                                        "核对区号和手机号。仍收不到短信时，使用官方 App 的帮助入口。")),
            .init(id: "issuer", icon: "exclamationmark.triangle",
                  title: language.text("Card linking rejected", "绑卡被拒绝"),
                  detail: language.text("Check the app's supported card types. The card issuer may need to approve linking. Contact the issuer or the payment app's support if verification fails.",
                                        "在官方 App 检查支持的卡种。绑卡可能需要发卡行验证，验证失败时联系发卡行或支付平台客服。")),
            .init(id: "identity", icon: "person.text.rectangle",
                  title: language.text("Identity details rejected", "证件核验失败"),
                  detail: language.text("Check that the selected document type, name and number match your document. Follow any correction instructions in the official app.",
                                        "核对证件类型、姓名和号码是否与证件一致，按官方 App 的修正提示继续。")),
        ]
    }

    /// When a payment fails (JT, 2026-11-25): only what an official or government page states, checked
    /// 2026-11-25. Amounts can change, so every number points to the payment page.
    static func paymentFailures(in language: LioLanguage) -> [LioPaymentGuideStep] {
        let pbocNews = LioPaymentGuideStep.Source(
            name: language.text("Guangdong government website: PBOC payment guide for foreign visitors (news, 2024)",
                                "广东省政府网转载：人民银行发布外籍来华人员支付指南（2024）"),
            url: URL(string: "https://www.gd.gov.cn/zwgk/zcjd/gnzcsd/content/post_4391477.html")!)
        let weixinHelp = LioPaymentGuideStep.Source(
            name: language.text("WeChat Help Center: international cards", "微信帮助中心：国际卡"),
            url: URL(string: "https://help.wechat.com/cgi-bin/micromsg-bin/oshelpcenter?t=help_center%2Fw_topic_detail&opcode=2&id=2307252mur7f2307257zfyfe&lang=en&plat=ios&Channel=helpcenter")!)
        return [
            .init(id: "scan-fails", icon: "qrcode.viewfinder",
                  title: language.text("If a QR payment won't go through", "扫码付不了时"),
                  detail: language.text("At shops showing the Visa, Mastercard or UnionPay logo, you can pay with that card directly instead. If there is no logo, ask the cashier whether cards are accepted.",
                                        "在有 Visa、Mastercard、银联等受理标识的商户，可以直接用对应的卡刷卡付款；没有标识的，可以问收银员能不能刷卡。"),
                  source: pbocNews),
            .init(id: "limit", icon: "gauge.with.dots.needle.67percent",
                  title: language.text("Over the limit", "超过限额"),
                  detail: language.text("Weixin Pay states that international cards can pay up to RMB 6,500 per payment, RMB 50,000 a month and RMB 65,000 a year. For Alipay's limit, check the payment page. For more, pay by card or in cash. Limits can change; check the payment page for the current one.",
                                        "微信支付写明，外卡单笔最多 6,500 元、每月累计 50,000 元、每年累计 65,000 元；支付宝的外卡限额请看付款页面。超过时请刷卡或付现金。限额可能调整，以付款页面显示为准。"),
                  source: weixinHelp),
            .init(id: "fee", icon: "percent",
                  title: language.text("A 3% fee was added", "多收了 3% 服务费"),
                  detail: language.text("This applies to payments with an international card in Alipay or Weixin Pay: up to RMB 200 has no service fee, and above RMB 200 a 3% fee is added. It is not a failed payment. Check the payment page for the final fee.",
                                        "这是支付宝、微信支付用外卡付款的规则：单笔不超过 200 元免服务费，超过 200 元收 3%。这不是付款失败；费用以付款页面显示为准。"),
                  source: .init(name: language.text("Guizhou Foreign Affairs Office guide for foreigners (Dec 2024)",
                                                    "贵州省外办外籍人士指南（2024 年 12 月）"),
                                url: URL(string: "https://www.eguizhou.gov.cn/2024-12/25/c_1059232.htm")!)),
            .init(id: "transfer", icon: "person.2.slash",
                  title: language.text("Transfers and red packets aren't supported", "转账和发红包用不了"),
                  detail: language.text("Weixin Pay states that international cards do not support transfers or red packets. To pay a person, you can pay in cash.",
                                        "微信支付写明，外卡不支持转账和发红包。需要给个人付钱时，可以改付现金。"),
                  source: weixinHelp),
            .init(id: "cash", icon: "banknote",
                  title: language.text("When you need cash", "需要现金时"),
                  detail: language.text("Withdraw yuan with your bank card at an ATM showing its card network's logo, or exchange foreign cash at a bank branch, exchange counter or exchange machine showing the currency exchange sign.",
                                        "可以用银行卡在有对应卡组织标识的 ATM 取人民币，也可以在有货币兑换标识的银行网点、兑换机构或自助兑换机，用外币现金换人民币。"),
                  source: pbocNews),
        ]
    }

    private func cardPath(in language: LioLanguage) -> String {
        switch self {
        case .alipay:
            language.text("In Alipay, open Me, then Bank Cards. If the menus look different, use the current official guide.",
                          "在支付宝打开「我的」，再进入「银行卡」。如菜单与说明不同，请查看当前官方指南。")
        case .weixin:
            language.text("In WeChat, look for Services under Me, then open Wallet and Bank Cards. Refer to the official guide if the menu differs.",
                          "在微信的「我」中找到「服务」，再进入「钱包」和「银行卡」。如菜单与说明不同，请查看官方指南。")
        }
    }
}
