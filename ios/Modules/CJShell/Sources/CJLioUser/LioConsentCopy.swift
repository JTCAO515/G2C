import Foundation

/// The wording of the consent pages, as approved in `docs/privacy/consent-screens.md` (#1961). A test checks every
/// string here against that file, so the page cannot drift from the approved text.
enum LioConsentCopy {
    static func title(_ l: LioLanguage) -> String { l.text("How your data is handled", "先看看你的数据怎么处理") }

    struct Item {
        let heading: String
        let body: String
    }

    static func items(_ l: LioLanguage) -> [Item] {
        [
            Item(heading: l.text("Who runs it", "谁在运营"),
                 body: l.text("Go2China is operated by Guangzhou Chuangjing Technology Co., Ltd. Contact: hello@go2china.space.",
                              "Go2China 由广州创竞科技有限公司运营。联系：hello@go2china.space。")),
            Item(heading: l.text("Where it is stored (needed to use account features)", "存在哪里（需要你同意才能使用账号相关功能）"),
                 body: l.text("Your account, chats, trips and memories are stored on our servers in Hong Kong, China, with daily backups in object storage in Hong Kong.",
                              "你的账号、对话、行程和记忆存放在我们位于中国香港的服务器，每日备份存放在中国香港的对象存储。")),
            Item(heading: l.text("AI processing (your choice; the app works without it)", "AI 处理（你来选，不开启也能使用 App）"),
                 body: l.text("Go2China uses Alibaba Cloud Model Studio (Qwen) to generate replies, translate and read menus. Your chat text and trip content, the text, voice and images you translate, menu photos, place names and addresses in taxi, hotel and metro-nearby search results, and place names, opening hours and station names in roadbooks are sent from our service in Hong Kong to Alibaba Cloud Model Studio in Beijing, mainland China, for processing. You can use the app without AI processing; chat, trip planning, memory suggestions, translation and the menu helper will not be available, and place names show in Chinese only. You can turn it on or off at any time under Me → Privacy.",
                              "Go2China 用阿里云百炼（通义千问）生成回答、翻译和识别菜单。你的对话文字和行程内容，翻译的文字、语音和图片，菜单照片，打车、酒店、地铁周边搜索结果里的地点名和地址，以及路书里的地点名、营业时间和地铁站名，会从我们在中国香港的服务发到中国大陆北京的阿里云百炼处理。不开启 AI 处理也能使用 App，只是聊天、行程规划、记忆建议、翻译和点餐不可用，地点名只显示中文。你可以随时在「我的」→「隐私」里开启或关闭。")),
            Item(heading: l.text("What we do not do", "我们不做什么"),
                 body: l.text("We do not sell your personal information or use it for advertising. Please do not enter health, ID or religious information, or information that identifies other people, in chats or translation.",
                              "我们不出售你的个人信息，也不用于广告。请不要在对话或翻译里填写健康、证件、宗教等敏感信息，或可识别他人的信息。")),
            Item(heading: l.text("Asked separately", "另行询问"),
                 body: l.text("Location and memory are not part of this consent. We ask you separately when they are needed.",
                              "位置和记忆不在这里同意，用到时我们会单独问你。")),
            Item(heading: l.text("Your choices", "你的选择"),
                 body: l.text("You can view, edit and delete memories, or close your account, under Me at any time. Withdrawing does not affect processing before withdrawal. Requests already sent cannot be recalled in transit, but we will help delete them as the law requires. Full policy: go2china.space/privacy.",
                              "你可以随时在「我的」里查看、修改和删除记忆，或注销账号。撤回不影响撤回前已进行的处理；已经发出的请求无法在传输途中召回，但我们会依法协助删除。完整政策：go2china.space/privacy。")),
        ]
    }

    static func agreeWithAI(_ l: LioLanguage) -> String { l.text("Agree and turn on AI processing", "同意，并开启 AI 处理") }
    static func agreeWithoutAI(_ l: LioLanguage) -> String { l.text("Agree, but keep AI processing off", "同意，暂不开启 AI 处理") }
    static func decline(_ l: LioLanguage) -> String { l.text("Don't agree", "不同意") }

    static func declined(_ l: LioLanguage) -> String {
        l.text("Account, chat and trip features need your data to be stored on our servers in Hong Kong, China. Without this you cannot use them. You can read the full policy first, or leave.",
               "账号、对话、行程等功能需要把数据存放在我们位于中国香港的服务器。不同意就无法使用这些功能。你可以先读完整政策，也可以退出。")
    }
    static func readPolicy(_ l: LioLanguage) -> String { l.text("Read the full policy", "看完整政策") }
    static func leave(_ l: LioLanguage) -> String { l.text("Leave", "退出") }

    // Me → Privacy
    static func privacyTitle(_ l: LioLanguage) -> String { l.text("Privacy", "隐私") }
    static func aiTitle(_ l: LioLanguage) -> String { l.text("AI processing", "AI 处理") }
    static func aiOnDetail(_ l: LioLanguage) -> String {
        l.text("On: your chats, translation content and the place names you look up are sent to Alibaba Cloud Model Studio in Beijing for processing.",
               "已开启：你的对话、翻译内容和查到的地点名会发到北京的阿里云百炼处理。")
    }
    static func aiOffDetail(_ l: LioLanguage) -> String {
        l.text("AI processing is off. You can turn it back on here.", "已关闭 AI 处理，可在这里重新开启。")
    }
    static func turnOffConfirm(_ l: LioLanguage) -> String {
        l.text("Chat, trip planning, translation and the menu helper will stop, and no new content will be sent to Alibaba Cloud Model Studio. Requests already sent cannot be recalled in transit, but we will help delete them as the law requires. Everything else keeps working; place names show in Chinese only.",
               "关闭后，聊天、行程规划、翻译和点餐会停用，不再向阿里云百炼发送新的内容。已经发出的请求无法在传输途中召回，但我们会依法协助删除。其他功能照常使用，地点名只显示中文。")
    }
    static func turnOff(_ l: LioLanguage) -> String { l.text("Turn off AI processing", "关闭 AI 处理") }
    static func cancel(_ l: LioLanguage) -> String { l.text("Cancel", "取消") }
    static func turnOnConfirm(_ l: LioLanguage) -> String {
        l.text("Once on, your chats and translation content are sent to Alibaba Cloud Model Studio in Beijing, mainland China, for processing.",
               "开启后，你的对话和翻译内容会发到中国大陆北京的阿里云百炼处理。")
    }
    static func turnOn(_ l: LioLanguage) -> String { l.text("Turn on", "开启") }

    /// Shown where an AI feature is stopped.
    static func aiOff(_ l: LioLanguage) -> String {
        l.text("AI processing is off. You can turn it back on under Me → Privacy.", "已关闭 AI 处理，可在「我的」→「隐私」里重新开启。")
    }
}
