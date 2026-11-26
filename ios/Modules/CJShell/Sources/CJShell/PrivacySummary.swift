import Foundation

/// #1880: the in-app privacy summary, aligned with the Go2China Privacy Policy 1.0 published on 2026-12-01.
/// Wording approved by the coordinator under JT's pre-authorisation (2026-11-26). Location wording follows the system
/// permission only, because the in-app location consent (`G2CLocationConsentEnabled`) is off in build 58.
public enum PrivacySummary {
    struct Paragraph {
        let id: String
        let title: String
        let text: String
    }

    static let policyURL = "https://go2china.space/privacy"

    public static func title(_ language: ShellLanguage) -> String { language.text("Privacy summary", "隐私摘要") }

    static func operatorLine(_ language: ShellLanguage) -> String {
        language.text("Go2China is operated by Guangzhou Chuangjing Technology Co., Ltd.", "Go2China 由广州创竞科技有限公司运营。")
    }

    static func intro(_ language: ShellLanguage) -> String {
        language.text("This is a short summary of the Go2China Privacy Policy. The full policy is at \(policyURL) .",
                      "这是 Go2China 隐私政策的简短摘要，完整政策见 \(policyURL) 。")
    }

    static func paragraphs(_ language: ShellLanguage) -> [Paragraph] {
        [
            Paragraph(id: "process", title: language.text("What we process", "我们处理什么"), text: language.text(
                "You sign in with an invite code, and your sign-in details stay in this device's keychain. We process what you send to Lio, the trips you save, memories you agree to keep, what you enter in the tools, and usage counts. Location is read only when you use Taxi or Nearby and allow it in the system prompt. For Taxi it goes to DiDi and for Nearby to AMap; it is not stored with your account.",
                "你用邀请码登录，登录凭据保存在本机钥匙串。我们处理你发给 Lio 的内容、你保存的行程、你同意保存的记忆、你在工具里输入的内容和用量计数。只有在你使用打车或附近、并在系统弹窗里允许后，才会读取位置；打车时发给滴滴，查找附近时发给高德，不和你的账号一起保存。")),
            Paragraph(id: "where", title: language.text("Where it is stored and who receives it", "存在哪、发给谁"), text: language.text(
                "Your data is stored in Hong Kong, China (Alibaba Cloud). To reply, translate and read menus, the content is sent to Alibaba Cloud Model Studio in Beijing. Tool searches go to AMap, DiDi and VariFlight in mainland China; these requests do not include your account.",
                "你的数据存放在中国香港（阿里云）。生成回答、翻译、识别菜单时，相关内容会发送到北京的阿里云百炼；工具查询会发给中国大陆的高德、滴滴、飞常准，这些请求不带你的账号。")),
            Paragraph(id: "not", title: language.text("What we don't do", "我们不做什么"), text: language.text(
                "We do not sell your information or use it for advertising. We do not collect passport or ID numbers, payment card numbers or your contacts.",
                "我们不出售你的信息，也不用于广告；不收集护照等证件号码、支付卡号或你的通讯录。")),
            Paragraph(id: "keep", title: language.text("How long we keep it", "保存多久"), text: language.text(
                "Chats, trips and memories are kept until you delete them or close your account. Backups roll over after 30 days.",
                "对话、行程和记忆保存到你删除或注销账号为止；备份按 30 天滚动。")),
            Paragraph(id: "choices", title: language.text("Your choices", "你的选择"), text: language.text(
                "You can delete memories and close your account in Me. You can turn off location for Go2China in system Settings. For anything else, email hello@go2china.space.",
                "你可以在「我的」里删除记忆、注销账号；在系统设置里关闭 Go2China 的定位权限。其他请求请发邮件至 hello@go2china.space。")),
            Paragraph(id: "adults", title: language.text("Adults only", "成年人使用"), text: language.text(
                "Go2China is for adults aged 18 and over.", "Go2China 面向 18 周岁及以上的成年人。")),
        ]
    }
}
