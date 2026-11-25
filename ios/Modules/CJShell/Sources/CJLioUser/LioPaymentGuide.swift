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

    /// When a payment fails (JT, 2026-11-25): only advice with an official or government source.
    /// Amounts can change, so every number points to the payment page.
    static func paymentFailures(in language: LioLanguage) -> [LioPaymentGuideStep] {
        let pbocGuide = LioPaymentGuideStep.Source(
            name: language.text("People's Bank of China payment guide for foreign visitors", "人民银行《外籍来华人员支付指南》"),
            url: URL(string: "https://www.gd.gov.cn/zwgk/zcjd/gnzcsd/content/post_4391477.html")!)
        return [
            .init(id: "declined", icon: "creditcard.trianglebadge.exclamationmark",
                  title: language.text("Payment declined", "付款被拒"),
                  detail: language.text("Card payments go through your card issuer, so a decline usually comes from the issuer. Contact your issuer or try another card. You can also pay in cash, or by card at a shop showing your card's logo.",
                                        "外卡付款要经过发卡行，被拒多半是发卡行没有放行。请联系发卡行或换一张卡；也可以付现金，或在有你卡片标识的商户直接刷卡。"),
                  source: pbocGuide),
            .init(id: "limit", icon: "gauge.with.dots.needle.67percent",
                  title: language.text("Over the limit", "超过限额"),
                  detail: language.text("With an international card in Alipay or Weixin Pay, one payment can be up to about US$5,000, and about US$50,000 a year. For more, pay by card or in cash. The limits can change; the payment page shows the current one.",
                                        "在支付宝或微信支付里用外卡，单笔最多约 5,000 美元，每年累计最多约 50,000 美元。超过时请刷卡或付现金。限额可能调整，以付款页面显示为准。"),
                  source: .init(name: language.text("Chinese government website, 1 March 2024", "中国政府网，2024 年 3 月 1 日"),
                                url: URL(string: "https://english.www.gov.cn/news/202403/01/content_WS65e1dacdc6d0868f4e8e487b.html")!)),
            .init(id: "unverified", icon: "person.badge.shield.checkmark",
                  title: language.text("Identity not verified yet", "还没做身份验证"),
                  detail: language.text("You can link a card and pay before verifying your identity, but only up to a lower total. Weixin Pay states RMB 15,000. If you will spend more, verify with your passport when the app asks; the payment page shows your current limit.",
                                        "不做身份验证也能绑卡付款，但累计额度较低，微信支付写明最多 15,000 元。花费较多时，请按 App 提示用护照完成验证；当前额度以付款页面显示为准。"),
                  source: .init(name: language.text("Weixin official blog", "微信官方博客"),
                                url: URL(string: "https://blog.wechat.com/2024/12/19/easy-pay-with-weixin-pay-link-your-international-bank-card-today/")!)),
            .init(id: "fee", icon: "percent",
                  title: language.text("A 3% fee was added", "多收了 3% 服务费"),
                  detail: language.text("This applies to payments with an international card in Alipay or Weixin Pay: up to RMB 200 has no service fee, and above RMB 200 a 3% fee is added. It is not a failed payment. The payment page shows the fee.",
                                        "这是支付宝、微信支付用外卡付款的规则：单笔不超过 200 元免服务费，超过 200 元收 3%。这不是付款失败；费用以付款页面显示为准。"),
                  source: .init(name: language.text("Shenzhen Nanshan District payment guide", "深圳市南山区政府支付指南"),
                                url: URL(string: "https://www.szns.gov.cn/english/news/latestnews/content/post_11240926.html")!)),
            .init(id: "transfer", icon: "person.2.slash",
                  title: language.text("Can't pay a person", "付给个人失败"),
                  detail: language.text("Weixin Pay states that international cards are for purchases, not transfers or red packets. If you are shown a personal code, ask for the shop's payment code, or pay in cash.",
                                        "微信支付写明，外卡只能用于消费，不能转账或发红包。如果对方给的是个人收款码，请问店家要商户收款码，或改付现金。"),
                  source: .init(name: language.text("WeChat Help Center: international cards", "微信帮助中心：国际卡"),
                                url: URL(string: "https://help.wechat.com/cgi-bin/micromsg-bin/oshelpcenter?opcode=2&id=2307252mur7f2307257zfyfe&lang=en&plat=ios&Channel=helpcenter")!)),
            .init(id: "cash", icon: "banknote",
                  title: language.text("When you need cash", "需要现金时"),
                  detail: language.text("Withdraw yuan at an ATM showing your card network's logo, or exchange foreign cash at a bank branch or exchange counter showing the currency exchange sign.",
                                        "可以在有你卡片组织标识的 ATM 取人民币，也可以到有货币兑换标识的银行网点或兑换点，用外币现金换人民币。"),
                  source: pbocGuide),
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
