import Foundation

struct LioPaymentGuideStep: Identifiable {
    let id: String
    let icon: String
    let title: String
    let detail: String
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
            URL(string: "https://www.tencent.com/en-us/articles/2202108.html")!
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
