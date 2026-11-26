struct LioTravelPhrase: Equatable, Identifiable, Sendable {
    let id: String
    let chinese: String
    let english: String

    init(_ id: String, _ chinese: String, _ english: String) {
        self.id = id
        self.chinese = chinese
        self.english = english
    }

    func text(in language: LioLanguage) -> String {
        language.text(english, chinese)
    }
}

enum LioPhraseCategory: String, CaseIterable, Identifiable {
    case dining, directions, taxi, shopping, healthcare, business

    var id: Self { self }

    func title(in language: LioLanguage) -> String {
        switch self {
        case .dining: language.text("Dining", "点菜")
        case .directions: language.text("Directions", "问路")
        case .taxi: language.text("Taxis", "打车")
        case .shopping: language.text("Shopping", "购物")
        case .healthcare: language.text("Seeing a doctor", "看病")
        case .business: language.text("Business", "商务")
        }
    }

    var icon: String {
        switch self {
        case .dining: "fork.knife"
        case .directions: "map"
        case .taxi: "car"
        case .shopping: "bag"
        case .healthcare: "cross.case"
        case .business: "briefcase"
        }
    }

    var phrases: [LioTravelPhrase] {
        switch self {
        case .dining:
            [
                .init("dining-menu", "请问，有英文菜单吗？", "Is there a menu in English?"),
                .init("dining-mild", "这道菜可以做成不辣的吗？", "Could you make this dish not spicy?"),
                .init("dining-vegetarian", "我吃素，有什么菜可以点？", "I'm vegetarian. Which dishes can I order?"),
                .init("dining-check", "您好，我们想结账。", "We'd like the check, please."),
            ]
        case .directions:
            [
                .init("directions-subway", "能告诉我最近的地铁站怎么走吗？", "How do I get to the nearest subway station?"),
                .init("directions-map", "请在地图上指一下我现在的位置。", "Please show me where I am on the map."),
                .init("directions-restroom", "请问，这附近哪里有洗手间？", "Excuse me, where's a restroom nearby?"),
                .init("directions-walk", "从这里走过去大概要多久？", "About how long does it take to walk there?"),
            ]
        case .taxi:
            [
                .init("taxi-address", "麻烦送我到这个地址。", "Please take me to this address."),
                .init("taxi-stop", "在这里停车就可以，谢谢。", "Please stop here. Thank you."),
                .init("taxi-terminal", "请到机场这个航站楼。", "Please go to this airport terminal."),
                .init("taxi-trunk", "可以帮我打开后备箱吗？", "Could you open the trunk for me?"),
            ]
        case .shopping:
            [
                .init("shopping-price", "请问这件的价格是多少？", "What's the price of this item?"),
                .init("shopping-size", "这款还有别的尺码吗？", "Do you have this in another size?"),
                .init("shopping-card", "这里可以用境外银行卡付款吗？", "Can I pay here with an international bank card?"),
                .init("shopping-printed-slip", "能给我一张购物小票吗？", "May I have a printed slip?"),
            ]
        case .healthcare:
            [
                .init("healthcare-doctor", "我想看医生，请问在哪里挂号？", "I'd like to see a doctor. Where do I register?"),
                .init("healthcare-english", "请问可以用英文沟通吗？", "Can we speak in English?"),
                .init("healthcare-allergy", "我对这种药过敏。", "I'm allergic to this medicine."),
                .init("healthcare-instructions", "请把给我的说明写下来。", "Please write down the instructions for me."),
            ]
        case .business:
            [
                .init("business-quote", "请问可以报一下这款产品的价格吗？", "Could you give me a quote for this product?"),
                .init("business-moq", "请问最小起订量是多少？", "What is the minimum order quantity?"),
                .init("business-lead-time", "下单后大概多久可以交货？", "How long does delivery take after we place an order?"),
                .init("business-sample", "可以先提供样品吗？费用怎么算？", "Could you provide a sample first? How is it charged?"),
                .init("business-payment", "请问付款方式是什么？可以先付定金吗？", "What are the payment terms? Can we pay a deposit first?"),
            ]
        }
    }
}
