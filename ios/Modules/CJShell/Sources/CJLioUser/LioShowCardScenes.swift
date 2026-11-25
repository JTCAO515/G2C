import Foundation

/// What a show card says (#1572): Chinese for the person being shown, English so the traveller knows what it says.
/// The driver sign (#1550) is one kind of show card.
struct LioShowCardContent: Equatable, Sendable {
    /// A short Chinese line above the main sentence, such as 请送我到这个火车站.
    var leadZH: String?
    /// The largest line.
    var mainZH: String
    /// Further Chinese lines, slightly smaller.
    var detailsZH: [String] = []
    /// The same request in English, small, for the traveller.
    var english: [String] = []
    /// A small note under the card, in both languages (the pharmacy cards carry their safety note here).
    var noteZH: String?
    var noteEN: String?

    static func driver(nameZH: String, nameEN: String?, addressZH: String?, requestZH: String?) -> Self {
        Self(leadZH: requestZH.flatMap(\.nonEmpty), mainZH: nameZH,
             detailsZH: [addressZH?.nonEmpty].compactMap { $0 },
             english: [nameEN?.nonEmpty].compactMap { $0 }.filter { $0 != nameZH })
    }
}

/// The places a traveller shows a card in.
enum LioShowCardScene: String, CaseIterable, Identifiable, Sendable {
    case hotel, pharmacy, restaurant, directions, bank

    var id: Self { self }

    var symbol: String {
        switch self {
        case .hotel: "bed.double"
        case .pharmacy: "cross.case"
        case .restaurant: "fork.knife"
        case .directions: "signpost.right"
        case .bank: "banknote"
        }
    }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .hotel: language.text("Hotel front desk", "酒店前台")
        case .pharmacy: language.text("Pharmacy", "药店")
        case .restaurant: language.text("Restaurant", "餐厅")
        case .directions: language.text("Asking the way", "问路")
        case .bank: language.text("Bank and money exchange", "银行与换汇")
        }
    }

    var cards: [LioShowCardKind] {
        LioShowCardKind.allCases.filter { $0.scene == self }
    }
}

/// One card. Declaration order is the order shown in each scene.
enum LioShowCardKind: String, CaseIterable, Identifiable, Sendable {
    case checkIn, extendStay, luggage, callTaxi
    case symptoms, sameMedicine, drugAllergy
    case noChilli, foodAllergy
    case howToGet, nearest, lost
    case exchange, atmCard, foreignCardATM

    var id: Self { self }

    var scene: LioShowCardScene {
        switch self {
        case .checkIn, .extendStay, .luggage, .callTaxi: .hotel
        case .symptoms, .sameMedicine, .drugAllergy: .pharmacy
        case .noChilli, .foodAllergy: .restaurant
        case .howToGet, .nearest, .lost: .directions
        case .exchange, .atmCard, .foreignCardATM: .bank
        }
    }

    var identifier: String { "lio.show-card." + rawValue }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .checkIn: language.text("Check in", "办理入住")
        case .extendStay: language.text("Extend my stay", "续住")
        case .luggage: language.text("Leave my luggage", "寄存行李")
        case .callTaxi: language.text("Call me a taxi", "帮我叫出租车")
        case .symptoms: language.text("My symptoms", "我的症状")
        case .sameMedicine: language.text("A medicine I use", "找我常用的药")
        case .drugAllergy: language.text("Medicine allergies", "药物过敏")
        case .noChilli: language.text("No chilli", "不要辣")
        case .foodAllergy: language.text("Food allergies", "食物过敏")
        case .howToGet: language.text("How do I get there?", "去这里怎么走")
        case .nearest: language.text("Where is the nearest…", "最近的……在哪")
        case .lost: language.text("I'm lost", "我迷路了")
        case .exchange: language.text("Exchange money", "换人民币")
        case .atmCard: language.text("ATM kept my card", "ATM 吞卡")
        case .foreignCardATM: language.text("Foreign cards at the ATM", "ATM 能否用外国卡")
        }
    }

    /// Which details the card can carry; the card reads well without any of them.
    var fields: [LioShowCardField] {
        switch self {
        case .checkIn: [.bookingName]
        case .extendStay: [.nights, .roomNumber]
        case .luggage: [.roomNumber, .pickUpTime]
        case .callTaxi: [.destination]
        case .symptoms: [.symptoms, .symptomDays]
        case .sameMedicine: [.medicineName]
        case .drugAllergy: [.drugAllergies]
        case .noChilli: [.spice]
        case .foodAllergy: [.foodAllergies]
        case .howToGet: [.place]
        case .nearest: [.nearest]
        case .lost: [.hotel]
        case .exchange: [.amount, .currency]
        case .atmCard: [.atmLocation]
        case .foreignCardATM: []
        }
    }

    // swiftlint:disable:next cyclomatic_complexity function_body_length
    func content(_ input: LioShowCardInput) -> LioShowCardContent {
        switch self {
        case .checkIn:
            var card = LioShowCardContent(mainZH: "您好，我有预订，想办理入住。",
                                          english: ["Hello, I have a reservation and would like to check in."])
            if let name = input.cleanBookingName {
                card.detailsZH.append("预订姓名：" + name)
                card.english.append("Reservation name: " + name)
            }
            card.detailsZH.append("这是我的护照。")
            card.english.append("Here is my passport.")
            return card
        case .extendStay:
            let nights = max(1, min(input.nights, 30))
            var card = LioShowCardContent(mainZH: "您好，我想续住 \(nights) 晚。",
                                          english: ["Hello, I'd like to extend my stay by \(nights) \(nights == 1 ? "night" : "nights")."])
            if let room = input.cleanRoomNumber {
                card.detailsZH.append("房间号：" + room)
                card.english.append("Room number: " + room)
            }
            card.detailsZH.append("请问可以吗？")
            card.english.append("Is that possible?")
            return card
        case .luggage:
            var card = LioShowCardContent(mainZH: "您好，我想寄存行李，可以吗？",
                                          english: ["Hello, may I leave my luggage here?"])
            if let room = input.cleanRoomNumber {
                card.detailsZH.append("房间号：" + room)
                card.english.append("Room number: " + room)
            }
            if let time = input.cleanPickUpTime {
                card.detailsZH.append("我大约 \(time) 回来取。")
                card.english.append("I'll come back for it at about \(time).")
            }
            return card
        case .callTaxi:
            var card = LioShowCardContent(mainZH: "您好，可以帮我叫一辆出租车吗？",
                                          english: ["Hello, could you call a taxi for me, please?"])
            if let destination = input.cleanDestination {
                card.detailsZH.append("目的地：" + destination)
                card.english.append("Destination: " + destination)
            }
            return card
        case .symptoms:
            var card = LioShowCardContent(mainZH: "您好，我有以下症状：", english: ["Hello, I have these symptoms:"])
            let symptoms = LioSymptom.allCases.filter(input.symptoms.contains)
            card.detailsZH += symptoms.map(\.chinese)
            card.english += symptoms.map(\.english)
            if let days = input.symptomDays {
                card.detailsZH.append(days.chinese)
                card.english.append(days.english)
            }
            card.detailsZH.append("请问有适合的非处方药吗？")
            card.english.append("Is there an over-the-counter product that might help?")
            return card.withPharmacyNote()
        case .sameMedicine:
            var card = LioShowCardContent(mainZH: "您好，这是我平时用的药。请问有相同成分的吗？",
                                          english: ["Hello, this is a medicine I normally use. Do you have one with the same active ingredient?"])
            if let name = input.cleanMedicineName {
                card.detailsZH.append("药名或成分：" + name)
                card.english.append("Name or ingredient: " + name)
            }
            return card.withPharmacyNote()
        case .drugAllergy:
            var card = LioShowCardContent(mainZH: "我对以下药物过敏，请帮我避开：",
                                          english: ["I'm allergic to these medicines. Please help me avoid them:"])
            let allergies = LioDrugAllergen.allCases.filter(input.drugAllergies.contains)
            card.detailsZH += allergies.map(\.chinese)
            card.english += allergies.map(\.english)
            return card.withPharmacyNote()
        case .noChilli:
            switch input.spice {
            case .none:
                return LioShowCardContent(mainZH: "请不要放辣椒，一点辣都不要。",
                                          detailsZH: ["谢谢！"], english: ["No chilli at all, please. Thank you!"])
            case .mild:
                return LioShowCardContent(mainZH: "请少放辣椒，只要一点点辣。",
                                          detailsZH: ["谢谢！"], english: ["Only a little chilli, please. Thank you!"])
            }
        case .foodAllergy:
            let allergies = LioFoodAllergen.allCases.filter(input.foodAllergies.contains)
            return LioShowCardContent(
                mainZH: "我对以下食物过敏，请不要放，包括调料、酱汁和高汤：",
                detailsZH: allergies.map(\.chinese),
                english: ["I'm allergic to the foods below. Please leave them out, including sauces, seasoning and stock:"]
                    + allergies.map(\.english),
                noteZH: "如果不确定，请告诉我。谢谢！", noteEN: "If you're not sure, please tell me. Thank you!")
        case .howToGet:
            var card = LioShowCardContent(mainZH: "您好，请问去这里怎么走？", english: ["Hello, how do I get here?"])
            if let place = input.cleanPlace {
                card.detailsZH.append(place)
                card.english.append(place)
            }
            card.detailsZH.append("可以在地图上指给我看吗？")
            card.english.append("Could you show me on a map?")
            return card
        case .nearest:
            let place = input.nearest
            return LioShowCardContent(mainZH: "您好，请问最近的\(place.chinese)在哪里？",
                                      detailsZH: ["可以给我指一下方向吗？"],
                                      english: ["Hello, where is the nearest \(place.english)?", "Could you point me in the right direction?"])
        case .lost:
            var card = LioShowCardContent(mainZH: "您好，我迷路了，想回我住的酒店。",
                                          english: ["Hello, I'm lost and need to get back to my hotel."])
            if let hotel = input.hotel {
                card.detailsZH.append(hotel.nameZH)
                if let address = hotel.addressZH?.nonEmpty { card.detailsZH.append(address) }
                card.english.append("My hotel is shown above in Chinese.")
            }
            card.detailsZH.append("可以告诉我怎么走，或者帮我叫一辆出租车吗？")
            card.english.append("Could you tell me how to get there, or help me get a taxi?")
            return card
        case .exchange:
            let currency = input.currency
            if let amount = input.cleanAmount {
                return LioShowCardContent(mainZH: "您好，我想把 \(amount) \(currency.chinese)换成人民币。",
                                          detailsZH: ["这是我的护照。"],
                                          english: ["Hello, I'd like to exchange \(amount) \(currency.english) for Chinese yuan.", "Here is my passport."])
            }
            return LioShowCardContent(mainZH: "您好，我想把\(currency.chinese)换成人民币。",
                                      detailsZH: ["这是我的护照。"],
                                      english: ["Hello, I'd like to exchange \(currency.english) for Chinese yuan.", "Here is my passport."])
        case .atmCard:
            var card = LioShowCardContent(mainZH: "您好，ATM 把我的银行卡吞了，请帮我处理。",
                                          english: ["Hello, the ATM kept my bank card. Could you help me, please?"])
            if let location = input.cleanATMLocation {
                card.detailsZH.append("ATM 位置：" + location)
                card.english.append("ATM location: " + location)
            }
            card.detailsZH.append("这是我的护照。")
            card.english.append("Here is my passport.")
            return card
        case .foreignCardATM:
            return LioShowCardContent(mainZH: "您好，请问这里的 ATM 可以用外国银行卡取人民币吗？",
                                      detailsZH: ["我的卡是 Visa 或 Mastercard。"],
                                      english: ["Hello, can I withdraw Chinese yuan with a foreign bank card at this ATM?",
                                                "My card is Visa or Mastercard."])
        }
    }
}

enum LioShowCardField: String, CaseIterable, Sendable {
    case bookingName, nights, roomNumber, pickUpTime, destination
    case symptoms, symptomDays, medicineName, drugAllergies
    case spice, foodAllergies
    case place, nearest, hotel
    case amount, currency, atmLocation
}

private extension LioShowCardContent {
    func withPharmacyNote() -> Self {
        var card = self
        card.noteZH = "本卡只说明症状和需求，不是诊断。用药请遵医嘱、咨询药师。"
        card.noteEN = "This card only describes my symptoms and what I am looking for; it is not a diagnosis. Please follow your doctor's advice and ask the pharmacist."
        return card
    }
}

/// The traveller's own details for the cards. Kept on this device only.
struct LioShowCardInput: Equatable, Sendable {
    struct Hotel: Equatable, Sendable {
        let nameZH: String
        let addressZH: String?
    }

    static let maximumTextLength = 60

    var hotel: Hotel?
    var bookingName: String?
    var nights = 1
    var roomNumber: String?
    var pickUpTime: String?
    var destinationZH: String?
    var symptoms: Set<LioSymptom> = []
    var symptomDays: LioSymptomDays?
    var medicineName: String?
    var drugAllergies: Set<LioDrugAllergen> = []
    var spice = LioSpiceLevel.none
    var foodAllergies: Set<LioFoodAllergen> = []
    var placeZH: String?
    var nearest = LioNearestPlace.metro
    var amount: String?
    var currency = LioExchangeCurrency.usd
    var atmLocation: String?

    init(hotel: Hotel? = nil, nights: Int = 1, destinationZH: String? = nil) {
        self.hotel = hotel
        self.nights = nights
        self.destinationZH = destinationZH
    }

    var cleanBookingName: String? { Self.clean(bookingName) }
    var cleanRoomNumber: String? { Self.clean(roomNumber) }
    var cleanPickUpTime: String? { Self.clean(pickUpTime) }
    var cleanDestination: String? { Self.clean(destinationZH) }
    var cleanMedicineName: String? { Self.clean(medicineName) }
    var cleanPlace: String? { Self.clean(placeZH) }
    var cleanATMLocation: String? { Self.clean(atmLocation) }
    /// Digits, a decimal point and thousands separators only.
    var cleanAmount: String? {
        guard let value = Self.clean(amount),
              value.allSatisfy({ $0.isASCII && ($0.isNumber || $0 == "." || $0 == ",") }),
              value.contains(where: \.isNumber) else { return nil }
        return value
    }

    static func clean(_ text: String?) -> String? {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines).nonEmpty else { return nil }
        return String(trimmed.prefix(maximumTextLength))
    }
}

/// Common symptoms a pharmacist can act on. Describes what the traveller feels, never what it is.
enum LioSymptom: String, CaseIterable, Identifiable, Sendable {
    case fever, headache, cough, soreThroat, runnyNose, diarrhoea, stomachAche, nausea, rash, insectBites, sunburn, smallCut
    var id: Self { self }
    var chinese: String {
        switch self {
        case .fever: "发烧"
        case .headache: "头痛"
        case .cough: "咳嗽"
        case .soreThroat: "喉咙痛"
        case .runnyNose: "流鼻涕、鼻塞"
        case .diarrhoea: "腹泻"
        case .stomachAche: "胃痛、肚子痛"
        case .nausea: "恶心、晕车"
        case .rash: "皮肤痒、起疹子"
        case .insectBites: "蚊虫叮咬"
        case .sunburn: "晒伤"
        case .smallCut: "小伤口、擦伤"
        }
    }
    var english: String {
        switch self {
        case .fever: "Fever"
        case .headache: "Headache"
        case .cough: "Cough"
        case .soreThroat: "Sore throat"
        case .runnyNose: "Runny or blocked nose"
        case .diarrhoea: "Diarrhoea"
        case .stomachAche: "Stomach ache"
        case .nausea: "Nausea or motion sickness"
        case .rash: "Itchy skin or a rash"
        case .insectBites: "Insect bites"
        case .sunburn: "Sunburn"
        case .smallCut: "A small cut or graze"
        }
    }
}

enum LioSymptomDays: String, CaseIterable, Identifiable, Sendable {
    case today, twoToThree, moreThanThree
    var id: Self { self }
    var chinese: String {
        switch self {
        case .today: "今天开始的"
        case .twoToThree: "已经 2–3 天"
        case .moreThanThree: "已经 3 天以上"
        }
    }
    var english: String {
        switch self {
        case .today: "Started today"
        case .twoToThree: "For 2–3 days"
        case .moreThanThree: "For more than 3 days"
        }
    }
}

enum LioDrugAllergen: String, CaseIterable, Identifiable, Sendable {
    case penicillin, cephalosporins, sulfa, aspirin, ibuprofen, codeine
    var id: Self { self }
    var chinese: String {
        switch self {
        case .penicillin: "青霉素"
        case .cephalosporins: "头孢类"
        case .sulfa: "磺胺类"
        case .aspirin: "阿司匹林"
        case .ibuprofen: "布洛芬"
        case .codeine: "可待因"
        }
    }
    var english: String {
        switch self {
        case .penicillin: "Penicillin"
        case .cephalosporins: "Cephalosporins"
        case .sulfa: "Sulfa drugs"
        case .aspirin: "Aspirin"
        case .ibuprofen: "Ibuprofen"
        case .codeine: "Codeine"
        }
    }
}

enum LioSpiceLevel: String, CaseIterable, Identifiable, Sendable {
    case none, mild
    var id: Self { self }
    func title(_ language: LioLanguage) -> String {
        switch self {
        case .none: language.text("Not spicy at all", "完全不辣")
        case .mild: language.text("A little spicy", "微辣")
        }
    }
}

/// Food allergens for the restaurant card. To be shared with the ordering line's card for the waiter.
enum LioFoodAllergen: String, CaseIterable, Identifiable, Sendable {
    case peanut, treeNuts, shellfish, fish, egg, milk, wheat, soy, sesame
    var id: Self { self }
    var chinese: String {
        switch self {
        case .peanut: "花生"
        case .treeNuts: "坚果（核桃、杏仁、腰果等）"
        case .shellfish: "虾蟹贝类"
        case .fish: "鱼"
        case .egg: "鸡蛋"
        case .milk: "牛奶和奶制品"
        case .wheat: "小麦（面粉、面条、酱油）"
        case .soy: "大豆和豆制品"
        case .sesame: "芝麻"
        }
    }
    var english: String {
        switch self {
        case .peanut: "Peanuts"
        case .treeNuts: "Tree nuts (walnuts, almonds, cashews…)"
        case .shellfish: "Shellfish"
        case .fish: "Fish"
        case .egg: "Eggs"
        case .milk: "Milk and dairy"
        case .wheat: "Wheat (flour, noodles, soy sauce)"
        case .soy: "Soy"
        case .sesame: "Sesame"
        }
    }
}

enum LioNearestPlace: String, CaseIterable, Identifiable, Sendable {
    case metro, toilet, atm, pharmacy, hospital, convenienceStore
    var id: Self { self }
    var chinese: String {
        switch self {
        case .metro: "地铁站"
        case .toilet: "洗手间"
        case .atm: "ATM 取款机"
        case .pharmacy: "药店"
        case .hospital: "医院"
        case .convenienceStore: "便利店"
        }
    }
    var english: String {
        switch self {
        case .metro: "metro station"
        case .toilet: "toilet"
        case .atm: "ATM"
        case .pharmacy: "pharmacy"
        case .hospital: "hospital"
        case .convenienceStore: "convenience store"
        }
    }
}

enum LioExchangeCurrency: String, CaseIterable, Identifiable, Sendable {
    case usd, eur, gbp, jpy, krw, hkd, aud, cad, sgd
    var id: Self { self }
    var chinese: String {
        switch self {
        case .usd: "美元"
        case .eur: "欧元"
        case .gbp: "英镑"
        case .jpy: "日元"
        case .krw: "韩元"
        case .hkd: "港币"
        case .aud: "澳元"
        case .cad: "加元"
        case .sgd: "新加坡元"
        }
    }
    var english: String {
        switch self {
        case .usd: "US dollars"
        case .eur: "euros"
        case .gbp: "British pounds"
        case .jpy: "Japanese yen"
        case .krw: "Korean won"
        case .hkd: "Hong Kong dollars"
        case .aud: "Australian dollars"
        case .cad: "Canadian dollars"
        case .sgd: "Singapore dollars"
        }
    }
}

extension String {
    fileprivate var nonEmpty: String? { isEmpty ? nil : self }
}
