import Foundation

// Menu ordering (点餐模式): photograph a menu, get each dish explained, see which dishes may not suit the
// user's dietary memory, then show staff a Chinese order card. Behind `G2CMenuOrderEnabled`, hidden by default.
//
// Privacy: dietary memory is matched on this device only and never sent with the menu photo. The photo
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

    var isLegible: Bool { nameZH != nil }
}

struct LioMenuReading: Sendable, Equatable {
    let dishes: [LioMenuDish]
    /// Made-up Debug data; the screen says so.
    var isSample = false
}

// MARK: - Dietary memory

/// One saved memory row, as `slot` and the user's own words. Only food slots are read.
struct LioMenuDietNote: Sendable, Equatable {
    let slot: String
    let text: String
}

enum LioMenuRestriction: String, Sendable, CaseIterable, Hashable {
    case noSpicy, halal, vegetarian, noPork, noBeef, noAlcohol, noCoriander
    case peanut, treeNut, shellfish, fish, egg, dairy, gluten, soy, sesame

    /// Allergies are only ever "may contain, check with staff".
    var isAllergy: Bool {
        switch self {
        case .peanut, .treeNut, .shellfish, .fish, .egg, .dairy, .gluten, .soy, .sesame: true
        default: false
        }
    }

    func text(_ language: LioLanguage) -> String {
        switch self {
        case .noSpicy: language.text("No spicy food", "不吃辣")
        case .halal: language.text("Halal", "清真")
        case .vegetarian: language.text("Vegetarian", "素食")
        case .noPork: language.text("No pork", "不吃猪肉")
        case .noBeef: language.text("No beef", "不吃牛肉")
        case .noAlcohol: language.text("No alcohol", "不含酒")
        case .noCoriander: language.text("No coriander", "不吃香菜")
        case .peanut: language.text("Peanut allergy", "花生过敏")
        case .treeNut: language.text("Tree nut allergy", "坚果过敏")
        case .shellfish: language.text("Shellfish allergy", "海鲜（虾蟹贝）过敏")
        case .fish: language.text("Fish allergy", "鱼类过敏")
        case .egg: language.text("Egg allergy", "鸡蛋过敏")
        case .dairy: language.text("Dairy allergy", "乳制品过敏")
        case .gluten: language.text("Gluten allergy", "麸质过敏")
        case .soy: language.text("Soy allergy", "大豆过敏")
        case .sesame: language.text("Sesame allergy", "芝麻过敏")
        }
    }

    /// The allergen named in a "may contain" warning.
    func allergen(_ language: LioLanguage) -> String {
        switch self {
        case .peanut: language.text("peanut", "花生")
        case .treeNut: language.text("tree nuts", "坚果")
        case .shellfish: language.text("shellfish", "虾蟹贝类")
        case .fish: language.text("fish", "鱼")
        case .egg: language.text("egg", "鸡蛋")
        case .dairy: language.text("dairy", "乳制品")
        case .gluten: language.text("gluten", "麸质")
        case .soy: language.text("soy", "大豆")
        case .sesame: language.text("sesame", "芝麻")
        default: text(language)
        }
    }
}

/// Maps the user's own memory words to restrictions with a fixed bilingual word list. Anything it cannot map
/// with confidence, including positive statements such as "能吃辣", is shown as written and not used.
enum LioMenuDiet {
    struct Read: Equatable, Sendable {
        var restrictions: [LioMenuRestriction] = []
        /// The memory words each restriction came from, shown next to it.
        var sources: [LioMenuRestriction: String] = [:]
        /// Food notes that are not mapped, shown as written.
        var unmatched: [String] = []
    }

    static let foodSlotPrefixes = ["diet.", "food.", "health."]

    static func read(_ notes: [LioMenuDietNote]) -> Read {
        var read = Read()
        for note in notes where foodSlotPrefixes.contains(where: note.slot.hasPrefix) {
            let text = note.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { continue }
            let found = restrictions(in: text)
            if found.isEmpty {
                if !read.unmatched.contains(text) { read.unmatched.append(text) }
                continue
            }
            for restriction in found where !read.restrictions.contains(restriction) {
                read.restrictions.append(restriction)
                read.sources[restriction] = text
            }
        }
        return read
    }

    private static let positive = ["能吃", "可以吃", "爱吃", "不怕辣", "不过敏", "没有过敏", "无过敏", "不忌口", "没有忌口",
                                   "not allergic", "no allerg", "love", "enjoy", "can eat", "fine with", "喜欢", " like "]
    private static let avoidance = ["不吃", "不能吃", "不要", "不喝", "忌", "避免", "怕", "过敏", "不含",
                                    "avoid", "allergic", "allergy", "intoleran", "no ", "not ", "don't", "do not",
                                    "can't", "cannot", "without", "free"]
    private static let words: [(LioMenuRestriction, [String])] = [
        (.noSpicy, ["吃辣", "不辣", "辣", "spicy", "spice", "chili", "chilli", "mild"]),
        (.halal, ["清真", "穆斯林", "halal", "muslim"]),
        (.vegetarian, ["素食", "吃素", "纯素", "vegetarian", "vegan"]),
        (.noPork, ["猪肉", "pork"]),
        (.noBeef, ["牛肉", "beef"]),
        (.noAlcohol, ["酒", "alcohol"]),
        (.noCoriander, ["香菜", "芫荽", "coriander", "cilantro"]),
        (.peanut, ["花生", "peanut"]),
        (.treeNut, ["坚果", "核桃", "腰果", "杏仁", "tree nut", "nuts", "walnut", "cashew", "almond"]),
        (.shellfish, ["海鲜", "虾", "蟹", "贝", "shellfish", "seafood", "shrimp", "prawn", "crab", "lobster"]),
        (.fish, ["鱼", "fish"]),
        (.egg, ["鸡蛋", "蛋", "egg"]),
        (.dairy, ["牛奶", "乳制品", "乳糖", "奶", "dairy", "milk", "lactose"]),
        (.gluten, ["麸质", "小麦", "面筋", "gluten", "wheat", "celiac", "coeliac"]),
        (.soy, ["大豆", "黄豆", "豆制品", "soy"]),
        (.sesame, ["芝麻", "sesame"]),
    ]
    /// Identity words that state a restriction on their own, without "no" or "allergic".
    private static let standalone: Set<LioMenuRestriction> = [.halal, .vegetarian]

    static func restrictions(in text: String) -> [LioMenuRestriction] {
        var value = " " + text.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "不喜欢", with: "避免")
            .replacingOccurrences(of: "don't like", with: "avoid")
            .replacingOccurrences(of: "dislike", with: "avoid") + " "
        if positive.contains(where: value.contains) { return [] }
        let avoids = avoidance.contains(where: value.contains)
        var found: [LioMenuRestriction] = []
        for (restriction, forms) in words {
            guard let form = forms.first(where: value.contains) else { continue }
            let mild = restriction == .noSpicy && ["不辣", "mild"].contains(form)
            guard avoids || mild || standalone.contains(restriction) else { continue }
            found.append(restriction)
            // "peanuts" must not also read as "nuts", nor "shellfish" as "fish"; "seafood" names fish too.
            if restriction == .peanut || restriction == .shellfish {
                value = value.replacingOccurrences(of: form, with: " ")
            }
            if restriction == .shellfish, ["海鲜", "seafood"].contains(form) { found.append(.fish) }
        }
        var unique: [LioMenuRestriction] = []
        for restriction in found where !unique.contains(restriction) { unique.append(restriction) }
        return unique
    }
}

// MARK: - Flags

enum LioMenuFlag: Hashable, Sendable {
    /// Clearly against a preference (spicy, pork for halal, meat for vegetarian).
    case unsuitable(LioMenuRestriction)
    /// Might be against a preference; ask staff.
    case check(LioMenuRestriction)
    /// Might contain an allergen; ask staff. Allergies never get a stronger or weaker wording.
    case mayContain(LioMenuRestriction)
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

    static func flags(for dish: LioMenuDish, restrictions: [LioMenuRestriction]) -> [LioMenuFlag] {
        guard dish.isLegible else { return [.unreadable] }
        return restrictions.compactMap { flag(for: dish, restriction: $0) }
    }

    private static func flag(for dish: LioMenuDish, restriction: LioMenuRestriction) -> LioMenuFlag? {
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
        case .peanut, .treeNut, .shellfish, .fish, .egg, .dairy, .gluten, .soy, .sesame:
            return contains[allergen(restriction)] != nil ? .mayContain(restriction) : nil
        }
    }

    private static func allergen(_ restriction: LioMenuRestriction) -> LioMenuIngredient {
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
enum LioMenuNote: String, Sendable, CaseIterable, Hashable {
    case noSpicy, lessSpicy, noCoriander, noScallion, noMSG, lessOil, vegetarian, halal, noPork, noAlcohol
    case allergyPeanut, allergyTreeNut, allergyShellfish, allergyFish, allergyEgg, allergyDairy, allergyGluten,
         allergySoy, allergySesame

    /// Everyday requests offered on every card.
    static let common: [LioMenuNote] = [.noSpicy, .lessSpicy, .noCoriander, .noScallion, .noMSG, .lessOil]

    var chinese: String {
        switch self {
        case .noSpicy: "不要辣"
        case .lessSpicy: "少放辣"
        case .noCoriander: "不要香菜"
        case .noScallion: "不要葱"
        case .noMSG: "不放味精"
        case .lessOil: "少油"
        case .vegetarian: "我吃素，请不要放肉，也不要用肉汤"
        case .halal: "我只吃清真食品，请不要放猪肉和酒"
        case .noPork: "我不吃猪肉"
        case .noAlcohol: "请不要放酒"
        case .allergyPeanut: "我对花生过敏，请不要放花生"
        case .allergyTreeNut: "我对坚果过敏，请不要放坚果"
        case .allergyShellfish: "我对虾蟹贝类过敏，请不要放"
        case .allergyFish: "我对鱼过敏，请不要放鱼"
        case .allergyEgg: "我对鸡蛋过敏，请不要放鸡蛋"
        case .allergyDairy: "我对奶制品过敏，请不要放牛奶、黄油"
        case .allergyGluten: "我对麸质过敏，请不要放小麦和面粉"
        case .allergySoy: "我对大豆过敏，请不要放酱油和豆制品"
        case .allergySesame: "我对芝麻过敏，请不要放芝麻和芝麻油"
        }
    }

    var english: String {
        switch self {
        case .noSpicy: "No chili"
        case .lessSpicy: "Less chili"
        case .noCoriander: "No coriander"
        case .noScallion: "No spring onion"
        case .noMSG: "No MSG"
        case .lessOil: "Less oil"
        case .vegetarian: "I'm vegetarian: no meat or meat broth"
        case .halal: "I only eat halal: no pork or alcohol"
        case .noPork: "I don't eat pork"
        case .noAlcohol: "No alcohol in the food"
        case .allergyPeanut: "I'm allergic to peanuts"
        case .allergyTreeNut: "I'm allergic to tree nuts"
        case .allergyShellfish: "I'm allergic to shellfish"
        case .allergyFish: "I'm allergic to fish"
        case .allergyEgg: "I'm allergic to eggs"
        case .allergyDairy: "I'm allergic to dairy"
        case .allergyGluten: "I'm allergic to gluten"
        case .allergySoy: "I'm allergic to soy"
        case .allergySesame: "I'm allergic to sesame"
        }
    }

    func text(_ language: LioLanguage) -> String { language == .english ? english : chinese }

    static func suggested(for restrictions: [LioMenuRestriction]) -> [LioMenuNote] {
        restrictions.compactMap { restriction in
            switch restriction {
            case .noSpicy: .noSpicy
            case .halal: .halal
            case .vegetarian: .vegetarian
            case .noPork: .noPork
            case .noBeef: nil
            case .noAlcohol: .noAlcohol
            case .noCoriander: .noCoriander
            case .peanut: .allergyPeanut
            case .treeNut: .allergyTreeNut
            case .shellfish: .allergyShellfish
            case .fish: .allergyFish
            case .egg: .allergyEgg
            case .dairy: .allergyDairy
            case .gluten: .allergyGluten
            case .soy: .allergySoy
            case .sesame: .allergySesame
            }
        }
    }
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
        let notes: [String]
        let closing = "谢谢！"
    }

    func card(in reading: LioMenuReading) -> Card {
        let names = Dictionary(uniqueKeysWithValues: reading.dishes.compactMap { dish in
            dish.nameZH.map { (dish.id, $0) }
        })
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
