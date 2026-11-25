import Foundation

/// The shared dietary vocabulary: what a traveller avoids or is allergic to, in Chinese and English, with the
/// sentence to show restaurant staff. Menu ordering and the show-staff cards both use it; the menu-ordering
/// line owns this file, so ask there to add a need or change a sentence.
enum LioDietaryNeed: String, Sendable, CaseIterable, Hashable {
    case noSpicy, halal, vegetarian, noPork, noBeef, noAlcohol, noCoriander
    case peanut, treeNut, shellfish, fish, egg, dairy, gluten, soy, sesame

    static let preferences: [LioDietaryNeed] = [.noSpicy, .halal, .vegetarian, .noPork, .noBeef, .noAlcohol,
                                                .noCoriander]
    static let allergies: [LioDietaryNeed] = [.peanut, .treeNut, .shellfish, .fish, .egg, .dairy, .gluten, .soy,
                                              .sesame]

    /// Allergies are only ever "may contain, check with staff".
    var isAllergy: Bool { Self.allergies.contains(self) }

    func text(_ language: LioLanguage) -> String {
        switch self {
        case .noSpicy: language.text("No spicy food", "不吃辣")
        case .halal: language.text("Halal", "清真")
        case .vegetarian: language.text("Vegetarian", "素食")
        case .noPork: language.text("No pork", "不吃猪肉")
        case .noBeef: language.text("No beef", "不吃牛肉")
        case .noAlcohol: language.text("No alcohol", "不含酒")
        case .noCoriander: language.text("No coriander", "不吃香菜")
        default: language.text("\(allergen(.english).capitalizedFirst) allergy", "\(allergen(.chinese))过敏")
        }
    }

    /// Where an allergen hides, for needs travellers often get wrong (soy sauce has wheat); `nil` otherwise.
    /// The show-staff cards print it next to the allergen.
    func examples(_ language: LioLanguage) -> String? {
        switch self {
        case .gluten: language.text("Wheat (flour, noodles, soy sauce)", "小麦（面粉、面条、酱油）")
        case .treeNut: language.text("Tree nuts (walnuts, almonds, cashews…)", "坚果（核桃、杏仁、腰果等）")
        default: nil
        }
    }

    /// The allergen named in a "may contain" warning; the need's own name for preferences.
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

    /// The Chinese sentence to show staff.
    var staffSentenceZH: String {
        switch self {
        case .noSpicy: "请不要放辣椒。"
        case .halal: "我只吃清真食品，请不要放猪肉和酒。"
        case .vegetarian: "我吃素，请不要放肉，也不要用肉汤。"
        case .noPork: "我不吃猪肉。"
        case .noBeef: "我不吃牛肉。"
        case .noAlcohol: "请不要放酒。"
        case .noCoriander: "请不要放香菜。"
        default: "我对\(allergen(.chinese))过敏，请不要放，包括调料和高汤。"
        }
    }

    /// What the Chinese sentence says, for the traveller.
    var staffSentenceEN: String {
        switch self {
        case .noSpicy: "No chilli, please."
        case .halal: "I only eat halal food: no pork or alcohol, please."
        case .vegetarian: "I'm vegetarian: no meat or meat broth, please."
        case .noPork: "I don't eat pork."
        case .noBeef: "I don't eat beef."
        case .noAlcohol: "No alcohol in the food, please."
        case .noCoriander: "No coriander, please."
        default: "I'm allergic to \(allergen(.english)). Please leave it out, including sauces and broth."
        }
    }
}

private extension String {
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}
