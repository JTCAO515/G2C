import Testing
@testable import CJLioUser

/// #1572: show cards for the hotel front desk, pharmacy, restaurant, directions and bank, Chinese large and
/// English below, filled in with the traveller's own details.
struct LioShowCardTests {
    private let hotel = LioShowCardInput.Hotel(nameZH: "北京王府井希尔顿酒店", addressZH: "北京市东城区王府井东街8号")

    @Test func everySceneHasCardsAndEveryCardHasBothLanguages() {
        #expect(LioShowCardScene.allCases == [.hotel, .pharmacy, .restaurant, .directions, .bank])
        for scene in LioShowCardScene.allCases {
            #expect(!scene.cards.isEmpty)
            #expect(!scene.title(.english).isEmpty && !scene.title(.chinese).isEmpty)
            #expect(!scene.symbol.isEmpty)
        }
        let all = LioShowCardScene.allCases.flatMap(\.cards)
        #expect(all.count == LioShowCardKind.allCases.count, "every card belongs to exactly one scene")
        #expect(Set(all).count == all.count)
        for kind in LioShowCardKind.allCases {
            #expect(!kind.title(.english).isEmpty && !kind.title(.chinese).isEmpty)
            let content = kind.content(LioShowCardInput())
            #expect(!content.mainZH.isEmpty && !content.english.isEmpty)
            #expect(kind.identifier.hasPrefix("lio.show-card."))
        }
        #expect(Set(LioShowCardKind.allCases.map(\.identifier)).count == LioShowCardKind.allCases.count)
    }

    @Test func noCardLeaksAPlaceholderOrAnEmptyLineWhenDetailsAreMissing() {
        for kind in LioShowCardKind.allCases {
            for input in [LioShowCardInput(), filledInput()] {
                let content = kind.content(input)
                let lines = [content.leadZH, content.mainZH, content.noteZH, content.noteEN].compactMap { $0 }
                    + content.detailsZH + content.english
                for line in lines {
                    #expect(!line.trimmingCharacters(in: .whitespaces).isEmpty, "\(kind) has an empty line")
                    #expect(!line.contains("{") && !line.contains("}") && !line.contains("nil")
                            && !line.contains("Optional("), "\(kind): \(line)")
                }
            }
        }
    }

    @Test func hotelCardsCarryTheHotelNameRoomAndNights() {
        var input = LioShowCardInput(hotel: hotel)
        input.roomNumber = "1208"
        input.nights = 2
        input.bookingName = "SMITH JOHN"
        let checkIn = LioShowCardKind.checkIn.content(input)
        #expect(checkIn.mainZH == "您好，我有预订，想办理入住。")
        #expect(checkIn.detailsZH.contains("预订姓名：SMITH JOHN"))
        #expect(checkIn.english.contains("Reservation name: SMITH JOHN"))

        let extend = LioShowCardKind.extendStay.content(input)
        #expect(extend.mainZH == "您好，我想续住 2 晚。")
        #expect(extend.detailsZH.contains("房间号：1208"))
        #expect(extend.english.first == "Hello, I'd like to extend my stay by 2 nights.")

        let one = LioShowCardKind.extendStay.content(LioShowCardInput(nights: 1))
        #expect(one.english.first == "Hello, I'd like to extend my stay by 1 night.")
        #expect(!one.detailsZH.contains { $0.hasPrefix("房间号") }, "no room line without a room number")
    }

    @Test func taxiAndLostCardsUseTheSavedHotelAddress() {
        let lost = LioShowCardKind.lost.content(LioShowCardInput(hotel: hotel))
        #expect(lost.detailsZH.contains("北京王府井希尔顿酒店"))
        #expect(lost.detailsZH.contains("北京市东城区王府井东街8号"))
        let taxi = LioShowCardKind.callTaxi.content(LioShowCardInput(destinationZH: "首都国际机场 T3"))
        #expect(taxi.detailsZH.contains("目的地：首都国际机场 T3"))
    }

    @Test func pharmacyCardsDescribeSymptomsAndNeedsButNeverDiagnoseOrPrescribe() {
        var input = filledInput()
        input.symptoms = [.fever, .soreThroat]
        input.symptomDays = .twoToThree
        let symptoms = LioShowCardKind.symptoms.content(input)
        #expect(symptoms.detailsZH.contains("发烧") && symptoms.detailsZH.contains("喉咙痛"))
        #expect(symptoms.english.contains("Fever") && symptoms.english.contains("Sore throat"))
        #expect(symptoms.detailsZH.contains("已经 2–3 天"))
        input.drugAllergies = [.penicillin]
        for kind in LioShowCardScene.pharmacy.cards {
            let content = kind.content(input)
            #expect(content.noteZH?.contains("请遵医嘱、咨询药师") == true, "\(kind)")
            #expect(content.noteEN?.contains("pharmacist") == true, "\(kind)")
            let chinese = ([content.leadZH, content.mainZH] + content.detailsZH).compactMap { $0 }.joined()
            let english = content.english.joined(separator: " ").lowercased()
            for word in ["诊断为", "建议服用", "建议吃", "应该吃", "剂量", "每次", "每日"] {
                #expect(!chinese.contains(word), "\(kind) must not diagnose or prescribe: \(word)")
            }
            for word in ["diagnos", "you should take", "dose", "dosage", "times a day"] {
                #expect(!english.contains(word), "\(kind) must not diagnose or prescribe: \(word)")
            }
        }
        let allergy = LioShowCardKind.drugAllergy.content(input)
        #expect(allergy.detailsZH.contains("青霉素") && allergy.english.contains("Penicillin"))
    }

    @Test func restaurantCardsListAllergensInBothLanguages() {
        var input = LioShowCardInput()
        input.foodAllergies = [.peanut, .shellfish]
        let allergy = LioShowCardKind.foodAllergy.content(input)
        #expect(allergy.detailsZH == ["花生", "虾蟹贝类"])
        #expect(allergy.english.contains("Peanuts") && allergy.english.contains("Shellfish"))
        #expect(allergy.mainZH.contains("过敏"))
        let spice = LioShowCardKind.noChilli.content(LioShowCardInput())
        #expect(spice.mainZH == "请不要放辣椒，一点辣都不要。")
        var mild = LioShowCardInput()
        mild.spice = .mild
        #expect(LioShowCardKind.noChilli.content(mild).mainZH == "请少放辣椒，只要一点点辣。")
    }

    @Test func listsKeepTheOrderTheyAreDeclaredIn() {
        var input = LioShowCardInput()
        input.foodAllergies = [.sesame, .peanut]
        #expect(LioShowCardKind.foodAllergy.content(input).detailsZH == ["花生", "芝麻"])
    }

    @Test func bankCardsCarryTheAmountAndCurrency() {
        var input = LioShowCardInput()
        input.amount = "500"
        input.currency = .usd
        let exchange = LioShowCardKind.exchange.content(input)
        #expect(exchange.mainZH == "您好，我想把 500 美元换成人民币。")
        #expect(exchange.english.first == "Hello, I'd like to exchange 500 US dollars for Chinese yuan.")
    }

    @Test func driverSignIsOneKindOfShowCard() {
        let content = LioShowCardContent.driver(nameZH: "北京南站", nameEN: "Beijing South Railway Station",
                                                addressZH: "北京市丰台区", requestZH: "请送我到这个火车站")
        #expect(content.leadZH == "请送我到这个火车站")
        #expect(content.mainZH == "北京南站")
        #expect(content.detailsZH == ["北京市丰台区"])
        #expect(content.english == ["Beijing South Railway Station"])
        let same = LioShowCardContent.driver(nameZH: "国贸", nameEN: "国贸", addressZH: "", requestZH: nil)
        #expect(same.detailsZH.isEmpty && same.english.isEmpty && same.leadZH == nil)
    }

    @Test func userTextIsTrimmedAndCapped() {
        var input = LioShowCardInput()
        input.roomNumber = "  1208  "
        input.bookingName = String(repeating: "A", count: 200)
        #expect(input.cleanRoomNumber == "1208")
        #expect((input.cleanBookingName?.count ?? 0) <= LioShowCardInput.maximumTextLength)
        input.roomNumber = "   "
        #expect(input.cleanRoomNumber == nil)
    }

    @Test func pharmacyConditionsShowOnlyWhenChosen() {
        var input = LioShowCardInput()
        input.symptoms = [.cough]
        for kind in [LioShowCardKind.symptoms, .sameMedicine] {
            let plain = kind.content(input)
            #expect(!plain.detailsZH.contains { $0.contains("怀孕") || $0.contains("哺乳") || $0.contains("孩子") })
        }
        input.conditions = [.forChild, .pregnant, .breastfeeding]
        input.childAge = " 6 "
        for kind in [LioShowCardKind.symptoms, .sameMedicine] {
            let content = kind.content(input)
            #expect(content.detailsZH.contains("我怀孕了。") && content.english.contains("I'm pregnant."))
            #expect(content.detailsZH.contains("我在哺乳期。") && content.english.contains("I'm breastfeeding."))
            #expect(content.detailsZH.contains("这是给孩子用的，孩子 6 岁。"))
            #expect(content.english.contains("This is for a child aged 6."))
        }
        input.childAge = "six"
        #expect(LioShowCardKind.symptoms.content(input).detailsZH.contains("这是给孩子用的。"), "only digits make an age")
    }

    @Test func emptySelectionsStillReadAsAWholeRequest() {
        let none = LioShowCardInput()
        #expect(LioShowCardKind.symptoms.content(none).mainZH == "您好，我身体不太舒服。")
        #expect(LioShowCardKind.drugAllergy.content(none).mainZH == "我对某些药物过敏。")
        #expect(LioShowCardKind.foodAllergy.content(none).mainZH == "我对某些食物过敏，请先跟我确认配料。")
        for kind in [LioShowCardKind.symptoms, .drugAllergy, .foodAllergy] {
            #expect(!kind.content(none).mainZH.hasSuffix("："), "\(kind) ends on a colon with nothing after it")
        }
    }

    @Test func exchangeUsesTheSingularForOne() {
        var input = LioShowCardInput()
        input.amount = "1"
        input.currency = .usd
        #expect(LioShowCardKind.exchange.content(input).english.first == "Hello, I'd like to exchange 1 US dollar for Chinese yuan.")
        input.currency = .jpy
        input.amount = "1,000"
        #expect(LioShowCardKind.exchange.content(input).english.first == "Hello, I'd like to exchange 1,000 Japanese yen for Chinese yuan.")
        input.amount = "-5"
        #expect(input.cleanAmount == nil)
        input.amount = "abc"
        #expect(input.cleanAmount == nil)
    }

    @Test func pickerTitlesReadNaturallyInEnglish() {
        #expect(LioNearestPlace.atm.title(.english) == "ATM")
        #expect(LioNearestPlace.metro.title(.english) == "Metro station")
        #expect(LioExchangeCurrency.usd.title(.english) == "US dollars")
        #expect(LioExchangeCurrency.eur.title(.english) == "Euros")
        #expect(LioExchangeCurrency.usd.title(.chinese) == "美元")
    }

    @Test func nearestAndForeignCardCards() {
        var input = LioShowCardInput()
        input.nearest = .toilet
        let nearest = LioShowCardKind.nearest.content(input)
        #expect(nearest.mainZH == "您好，请问最近的洗手间在哪里？")
        #expect(nearest.english.first == "Hello, where is the nearest toilet?")
        let foreign = LioShowCardKind.foreignCardATM.content(input)
        #expect(foreign.mainZH == "您好，请问这里的 ATM 可以用外国银行卡取人民币吗？")
        #expect(foreign.detailsZH == ["我的卡是外国银行卡（比如 Visa、Mastercard）。"])
    }

    private func filledInput() -> LioShowCardInput {
        var input = LioShowCardInput(hotel: hotel)
        input.roomNumber = "1208"
        input.bookingName = "SMITH JOHN"
        input.nights = 3
        input.pickUpTime = "18:00"
        input.destinationZH = "故宫博物院"
        input.symptoms = [.cough]
        input.symptomDays = .today
        input.medicineName = "Ibuprofen 200 mg"
        input.drugAllergies = [.aspirin]
        input.foodAllergies = [.peanut]
        input.placeZH = "天安门"
        input.nearest = .toilet
        input.amount = "100"
        input.currency = .eur
        input.atmLocation = "王府井大街 ATM"
        input.conditions = [.pregnant]
        input.childAge = "4"
        return input
    }
}
