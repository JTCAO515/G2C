import Foundation

// Menu ordering (点餐模式): photograph a menu, get each dish explained, see which dishes may not suit the
// user's dietary memory, then show staff a Chinese order card. Behind `G2CMenuOrderEnabled`, hidden by default.
//
// Privacy: dietary needs are matched on this device only and never sent with the menu photo. The photo
// goes only to the authorised model relay and is not kept.

// MARK: - Dishes

enum LioMenuSpice: Int, Sendable, CaseIterable, Comparable {
    case notSpicy, mild, medium, hot

    static func < (lhs: Self, rhs: Self) -> Bool { lhs.rawValue < rhs.rawValue }

    func text(_ language: LioLanguage) -> String {
        switch self {
        case .notSpicy: language.text("Not spicy", "不辣")
        case .mild: language.text("Mildly spicy", "微辣")
        case .medium: language.text("Spicy", "中辣")
        case .hot: language.text("Very spicy", "很辣")
        }
    }
}

/// Ingredients the model may report. The model says how sure it is; the app never says a dish is free of one.
enum LioMenuIngredient: String, Sendable, CaseIterable {
    case pork, beef, lamb, poultry, fish, shellfish, peanut, treeNut, egg, dairy, gluten, soy, sesame, alcohol,
         coriander, animalBroth

    static let meat: Set<Self> = [.pork, .beef, .lamb, .poultry, .fish, .shellfish]
}

enum LioMenuCertainty: Sendable, Equatable {
    /// A usual ingredient of this dish.
    case likely
    /// Often used (oil, broth, garnish) but not always.
    case possible
}

struct LioMenuDish: Identifiable, Sendable, Equatable {
    let id: String
    /// The dish name as printed, in Chinese. `nil` when the photo could not be read: never guessed.
    let nameZH: String?
    let nameEN: String
    let summaryEN: String
    let summaryZH: String
    let ingredientsEN: String
    let ingredientsZH: String
    let methodEN: String
    let methodZH: String
    let portionEN: String
    let portionZH: String
    /// `nil` when the spice level is not known.
    let spice: LioMenuSpice?
    let contains: [LioMenuIngredient: LioMenuCertainty]
    /// The price exactly as printed, if any.
    let priceText: String?

    /// A missing or blank Chinese name is unreadable, whatever else came back.
    var isLegible: Bool { !(nameZH ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
}

struct LioMenuReading: Sendable, Equatable {
    let dishes: [LioMenuDish]
    /// Made-up Debug data; the screen says so.
    var isSample = false
}

// MARK: - Dietary needs

/// One saved memory row, as `slot` and the user's own words.
struct LioMenuDietNote: Sendable, Equatable {
    let slot: String
    let text: String
}

/// The user picks their needs on the page. Saved memory can only pre-select "no spicy food": the only food
/// memory with that meaning is `diet.spicy`. `diet.taste` is taste and cuisine, not a restriction, and health
/// memory is sensitive, so neither is ever read here. Nothing read here is stored or sent.
enum LioMenuMemory {
    static let spicySlot = "diet.spicy"

    /// The memory words that say the user avoids spicy food, or `nil`.
    static func noSpicySource(_ notes: [LioMenuDietNote]) -> String? {
        notes.first { $0.slot == spicySlot && avoidsSpice($0.text) }?.text
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static let avoid = ["不吃辣", "不能吃辣", "不可以吃辣", "吃不了辣", "不要辣", "不辣", "忌辣", "怕辣", "少辣",
                                "微辣", "no spicy", "not spicy", "non-spicy", "avoid spicy", "don't eat spicy",
                                "do not eat spicy", "can't eat spicy", "cannot eat spicy", "can't handle spicy",
                                "cannot handle spicy", "no chili", "no chilli", "mild"]

    /// Any avoiding form counts, even beside a positive one ("不能吃辣" contains "能吃辣"): when unsure,
    /// "no spicy" is the safer reading, and the user sees the memory words and can untick it.
    static func avoidsSpice(_ text: String) -> Bool {
        var value = text.lowercased().replacingOccurrences(of: "’", with: "'")
        // "不怕辣" (not afraid of spice) contains "怕辣"; take it out before looking for negative forms.
        value = value.replacingOccurrences(of: "不怕辣", with: "〇")
        return avoid.contains(where: value.contains)
    }
}

// MARK: - Flags

enum LioMenuFlag: Hashable, Sendable {
    /// Clearly against a preference (spicy, pork for halal, meat for vegetarian).
    case unsuitable(LioDietaryNeed)
    /// Might be against a preference; ask staff.
    case check(LioDietaryNeed)
    /// Might contain an allergen; ask staff. Allergies never get a stronger or weaker wording.
    case mayContain(LioDietaryNeed)
    /// The dish name could not be read; ask staff.
    case unreadable

    var isWarning: Bool {
        if case .unsuitable = self { true } else { false }
    }

    func text(_ language: LioLanguage) -> String {
        switch self {
        case .unsuitable(let restriction):
            language.text("Not suitable: \(restriction.text(.english))", "不适合「\(restriction.text(.chinese))」")
        case .check(let restriction):
            language.text("May not suit \(restriction.text(.english)) — please check with staff",
                          "可能不适合「\(restriction.text(.chinese))」，请向服务员确认")
        case .mayContain(let restriction):
            language.text("May contain \(restriction.allergen(.english)) — please check with staff",
                          "可能含有\(restriction.allergen(.chinese))，请向服务员确认")
        case .unreadable:
            language.text("Couldn't read this — please ask staff", "看不清，请问服务员")
        }
    }

    static func flags(for dish: LioMenuDish, restrictions: [LioDietaryNeed]) -> [LioMenuFlag] {
        guard dish.isLegible else { return [.unreadable] }
        return restrictions.compactMap { flag(for: dish, restriction: $0) }
    }

    private static func flag(for dish: LioMenuDish, restriction: LioDietaryNeed) -> LioMenuFlag? {
        let contains = dish.contains
        func graded(_ ingredients: Set<LioMenuIngredient>) -> LioMenuFlag? {
            let found = ingredients.compactMap { contains[$0] }
            if found.contains(.likely) { return .unsuitable(restriction) }
            return found.isEmpty ? nil : .check(restriction)
        }
        switch restriction {
        case .noSpicy:
            guard let spice = dish.spice else { return .check(restriction) }
            switch spice {
            case .notSpicy: return nil
            case .mild: return .check(restriction)
            case .medium, .hot: return .unsuitable(restriction)
            }
        case .halal:
            if contains[.pork] == .likely { return .unsuitable(restriction) }
            // Whether other meat is halal cannot be read from a menu.
            let questions: Set<LioMenuIngredient> = [.pork, .beef, .lamb, .poultry, .alcohol, .animalBroth]
            return questions.contains { contains[$0] != nil } ? .check(restriction) : nil
        case .vegetarian:
            if let meat = graded(LioMenuIngredient.meat) { return meat }
            return contains[.animalBroth] != nil ? .check(restriction) : nil
        case .noPork: return graded([.pork])
        case .noBeef: return graded([.beef])
        case .noAlcohol: return graded([.alcohol])
        case .noCoriander:
            // Coriander is a garnish staff can leave out.
            return contains[.coriander] != nil ? .check(restriction) : nil
        case .treeNut:
            // Many people with a nut allergy also avoid peanuts, and menus mix them up.
            return contains[.treeNut] != nil || contains[.peanut] != nil ? .mayContain(restriction) : nil
        case .peanut, .shellfish, .fish, .egg, .dairy, .gluten, .soy, .sesame:
            return contains[allergen(restriction)] != nil ? .mayContain(restriction) : nil
        }
    }

    private static func allergen(_ restriction: LioDietaryNeed) -> LioMenuIngredient {
        switch restriction {
        case .peanut: .peanut
        case .treeNut: .treeNut
        case .shellfish: .shellfish
        case .fish: .fish
        case .egg: .egg
        case .dairy: .dairy
        case .gluten: .gluten
        case .soy: .soy
        default: .sesame
        }
    }
}

// MARK: - Order card

/// A Chinese note for staff, with its English meaning for the user.
enum LioMenuNote: Hashable, Sendable {
    case lessSpicy, noScallion, noMSG, lessOil
    /// A dietary need, written as the shared staff sentence.
    case need(LioDietaryNeed)

    /// Everyday requests offered on every card.
    static let common: [LioMenuNote] = [.need(.noSpicy), .lessSpicy, .need(.noCoriander), .noScallion, .noMSG, .lessOil]

    var id: String {
        switch self {
        case .lessSpicy: "lessSpicy"
        case .noScallion: "noScallion"
        case .noMSG: "noMSG"
        case .lessOil: "lessOil"
        case .need(let need): need.rawValue
        }
    }

    var chinese: String {
        switch self {
        case .lessSpicy: "请少放辣。"
        case .noScallion: "请不要放葱。"
        case .noMSG: "请不要放味精。"
        case .lessOil: "请少放油。"
        case .need(let need): need.staffSentenceZH
        }
    }

    var english: String {
        switch self {
        case .lessSpicy: "Less chilli, please."
        case .noScallion: "No spring onion, please."
        case .noMSG: "No MSG, please."
        case .lessOil: "Less oil, please."
        case .need(let need): need.staffSentenceEN
        }
    }

    static func suggested(for needs: [LioDietaryNeed]) -> [LioMenuNote] { needs.map { .need($0) } }
}

struct LioMenuOrder: Equatable, Sendable {
    static let maximumQuantity = 20

    private(set) var dishIDs: [String] = []
    private(set) var quantities: [String: Int] = [:]
    private(set) var notes: [LioMenuNote] = []

    var isEmpty: Bool { dishIDs.isEmpty }
    var count: Int { quantities.values.reduce(0, +) }

    func quantity(of dish: LioMenuDish) -> Int { quantities[dish.id] ?? 0 }

    /// Only dishes whose Chinese name was read can go on the card.
    mutating func add(_ dish: LioMenuDish) {
        guard dish.isLegible else { return }
        let current = quantity(of: dish)
        guard current < Self.maximumQuantity else { return }
        if current == 0 { dishIDs.append(dish.id) }
        quantities[dish.id] = current + 1
    }

    mutating func remove(_ dish: LioMenuDish) {
        let current = quantity(of: dish)
        guard current > 0 else { return }
        if current == 1 {
            quantities[dish.id] = nil
            dishIDs.removeAll { $0 == dish.id }
        } else {
            quantities[dish.id] = current - 1
        }
    }

    func has(_ note: LioMenuNote) -> Bool { notes.contains(note) }

    mutating func toggle(_ note: LioMenuNote) {
        if let index = notes.firstIndex(of: note) { notes.remove(at: index) } else { notes.append(note) }
    }

    struct Card: Equatable, Sendable {
        let greeting = "您好，我想点这些菜："
        let lines: [String]
        /// Full sentences, one per line.
        let notes: [String]
        let closing = "谢谢！"
    }

    func card(in reading: LioMenuReading) -> Card {
        let names = Dictionary(reading.dishes.filter(\.isLegible).map { ($0.id, $0.nameZH ?? "") },
                               uniquingKeysWith: { first, _ in first })
        let lines = dishIDs.compactMap { id in names[id].map { "\($0) × \(quantities[id] ?? 0)" } }
        return Card(lines: lines, notes: notes.map(\.chinese))
    }
}

// MARK: - Service

struct LioMenuService: Sendable {
    let read: @Sendable (Data) async throws -> LioMenuReading

    /// The service for this build, or `nil` to hide the tool. The real relay is connected after JT approves the
    /// model authorisation; until then only Debug's `--lio-menu-preview` shows sample data.
    static func fromBuild(arguments: [String] = ProcessInfo.processInfo.arguments,
                          info: [String: Any]? = Bundle.main.infoDictionary,
                          relay: LioMenuService? = nil) -> LioMenuService? {
        #if DEBUG
        if arguments.contains("--lio-menu-preview") { return .preview }
        #endif
        guard info?["G2CMenuOrderEnabled"] as? String == "YES" else { return nil }
        return relay
    }
}
