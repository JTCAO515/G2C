import Foundation
import Testing
@testable import CJLioUser

/// Menu ordering (点餐模式): explain dishes, flag them against the user's dietary memory, build a waiter card.
struct LioMenuDietTests {
    private func note(_ text: String, slot: String = "diet.taste") -> LioMenuDietNote {
        LioMenuDietNote(slot: slot, text: text)
    }

    @Test func mapsCommonChineseAndEnglishRestrictions() {
        let read = LioMenuDiet.read([
            note("不吃辣", slot: "diet.spicy"), note("对花生过敏"), note("I'm allergic to shellfish"),
            note("清真"), note("Vegetarian"), note("不要香菜"),
        ])
        #expect(read.restrictions == [.noSpicy, .peanut, .shellfish, .halal, .vegetarian, .noCoriander])
        #expect(read.unmatched.isEmpty)
        #expect(read.sources[.peanut] == "对花生过敏")
    }

    @Test func negatedOrPositiveStatementsAreNotTurnedIntoRestrictions() {
        let read = LioMenuDiet.read([
            note("能吃辣", slot: "diet.spicy"), note("I love spicy food", slot: "diet.spicy"),
            note("没有过敏"), note("not allergic to peanuts"), note("喜欢海鲜"),
        ])
        // Shown as written under "other food notes", never turned into a restriction.
        #expect(read.restrictions.isEmpty)
        #expect(read.unmatched.count == 5)
    }

    @Test func unknownFoodNotesAreShownAsWrittenNotGuessed() {
        let read = LioMenuDiet.read([note("少油少盐"), note("prefers window seats", slot: "trip.seat")])
        #expect(read.restrictions.isEmpty)
        #expect(read.unmatched == ["少油少盐"])
    }

    @Test func onlyFoodSlotsAreRead() {
        let read = LioMenuDiet.read([note("对花生过敏", slot: "trip.hotel")])
        #expect(read.restrictions.isEmpty)
        #expect(read.unmatched.isEmpty)
    }
}

struct LioMenuFlagTests {
    private func dish(_ contains: [LioMenuIngredient: LioMenuCertainty] = [:], spice: LioMenuSpice? = .notSpicy,
                      legible: Bool = true) -> LioMenuDish {
        LioMenuDish(id: "d", nameZH: legible ? "宫保鸡丁" : nil, nameEN: "Kung Pao Chicken",
                    summaryEN: "", summaryZH: "", ingredientsEN: "", ingredientsZH: "", methodEN: "", methodZH: "",
                    portionEN: "", portionZH: "", spice: spice, contains: contains, priceText: nil)
    }

    @Test func allergiesAreAlwaysMayContainAndAskStaff() {
        let flags = LioMenuFlag.flags(for: dish([.peanut: .likely]), restrictions: [.peanut])
        #expect(flags == [.mayContain(.peanut)])
        #expect(LioMenuFlag.mayContain(.peanut).text(.chinese) == "可能含有花生，请向服务员确认")
        let possible = LioMenuFlag.flags(for: dish([.peanut: .possible]), restrictions: [.peanut])
        #expect(possible == [.mayContain(.peanut)])
    }

    @Test func preferencesAreUnsuitableWhenLikelyAndMayContainWhenPossible() {
        #expect(LioMenuFlag.flags(for: dish([.pork: .likely]), restrictions: [.halal]) == [.unsuitable(.halal)])
        #expect(LioMenuFlag.flags(for: dish([.pork: .possible]), restrictions: [.halal]) == [.check(.halal)])
        #expect(LioMenuFlag.flags(for: dish([.poultry: .likely]), restrictions: [.vegetarian]) == [.unsuitable(.vegetarian)])
        #expect(LioMenuFlag.flags(for: dish([.animalBroth: .possible]), restrictions: [.vegetarian]) == [.check(.vegetarian)])
        // Halal slaughter cannot be read from a menu: other meat is a question for staff, not a verdict.
        #expect(LioMenuFlag.flags(for: dish([.beef: .likely]), restrictions: [.halal]) == [.check(.halal)])
    }

    @Test func spiceLevels() {
        #expect(LioMenuFlag.flags(for: dish(spice: .hot), restrictions: [.noSpicy]) == [.unsuitable(.noSpicy)])
        #expect(LioMenuFlag.flags(for: dish(spice: .medium), restrictions: [.noSpicy]) == [.unsuitable(.noSpicy)])
        #expect(LioMenuFlag.flags(for: dish(spice: .mild), restrictions: [.noSpicy]) == [.check(.noSpicy)])
        #expect(LioMenuFlag.flags(for: dish(spice: nil), restrictions: [.noSpicy]) == [.check(.noSpicy)])
        #expect(LioMenuFlag.flags(for: dish(spice: .notSpicy), restrictions: [.noSpicy]).isEmpty)
    }

    @Test func unreadableDishesAskStaffAndAreNeverJudged() {
        let flags = LioMenuFlag.flags(for: dish([.peanut: .likely], legible: false), restrictions: [.peanut])
        #expect(flags == [.unreadable])
        #expect(LioMenuFlag.unreadable.text(.chinese) == "看不清，请问服务员")
    }

    @Test func noRestrictionsMeansNoFlagsAndNothingIsCalledSafe() {
        #expect(LioMenuFlag.flags(for: dish([.peanut: .likely]), restrictions: []).isEmpty)
        let all = LioMenuRestriction.allCases.map { LioMenuFlag.check($0).text(.english) }
            + LioMenuRestriction.allCases.map { LioMenuFlag.unsuitable($0).text(.english) }
        #expect(all.allSatisfy { !$0.localizedCaseInsensitiveContains("safe") })
    }

    @Test func flagsFollowRestrictionOrderAndDoNotRepeat() {
        let flags = LioMenuFlag.flags(for: dish([.peanut: .likely, .pork: .likely], spice: .hot),
                                      restrictions: [.noSpicy, .peanut, .halal, .vegetarian])
        #expect(flags == [.unsuitable(.noSpicy), .mayContain(.peanut), .unsuitable(.halal), .unsuitable(.vegetarian)])
    }
}

struct LioMenuOrderCardTests {
    @Test func waiterCardListsChineseNamesQuantitiesAndNotes() throws {
        var order = LioMenuOrder()
        let reading = LioMenuReading.sample
        let kungPao = try #require(reading.dishes.first { $0.nameZH == "宫保鸡丁" })
        let rice = try #require(reading.dishes.first { $0.nameZH == "蛋炒饭" })
        order.add(kungPao)
        order.add(rice)
        order.add(rice)
        order.toggle(.noSpicy)
        order.toggle(.noCoriander)
        let card = order.card(in: reading)
        #expect(card.lines == ["宫保鸡丁 × 1", "蛋炒饭 × 2"])
        #expect(card.notes == ["不要辣", "不要香菜"])
        #expect(card.greeting == "您好，我想点这些菜：")
        #expect(order.count == 3)
    }

    @Test func quantitiesAreBoundedAndRemovable() throws {
        var order = LioMenuOrder()
        let dish = try #require(LioMenuReading.sample.dishes.first { $0.nameZH != nil })
        for _ in 0..<30 { order.add(dish) }
        #expect(order.quantity(of: dish) == LioMenuOrder.maximumQuantity)
        for _ in 0..<40 { order.remove(dish) }
        #expect(order.quantity(of: dish) == 0)
        #expect(order.isEmpty)
    }

    @Test func unreadableDishesCannotBeOrderedByName() throws {
        var order = LioMenuOrder()
        let unreadable = try #require(LioMenuReading.sample.dishes.first { $0.nameZH == nil })
        order.add(unreadable)
        #expect(order.isEmpty)
    }

    @Test func suggestedNotesFollowRestrictions() {
        #expect(LioMenuNote.suggested(for: [.noSpicy, .peanut, .vegetarian]) == [.noSpicy, .allergyPeanut, .vegetarian])
        #expect(LioMenuNote.allergyPeanut.chinese == "我对花生过敏，请不要放花生")
    }
}

struct LioMenuServiceBuildTests {
    @Test func hiddenUnlessTheBuildTurnsItOn() {
        #expect(LioMenuService.fromBuild(arguments: [], info: [:]) == nil)
        #expect(LioMenuService.fromBuild(arguments: [], info: ["G2CMenuOrderEnabled": "NO"]) == nil)
        #expect(LioMenuService.fromBuild(arguments: [], info: ["G2CMenuOrderEnabled": "$(G2C_MENU_ORDER_ENABLED)"]) == nil)
    }

    @Test func debugPreviewReturnsSampleMenuMarkedAsSample() async throws {
        let service = try #require(LioMenuService.fromBuild(arguments: ["--lio-menu-preview"], info: nil))
        let reading = try await service.read(Data([0xff, 0xd8, 0xff, 0x00]))
        #expect(reading.isSample)
        #expect(reading.dishes.contains { $0.nameZH == nil })
    }
}
