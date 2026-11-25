#if DEBUG
import Foundation

/// Debug-only sample menu for `--lio-menu-preview`. Dishes and prices are made up and the screen says so;
/// real readings come from the menu relay once JT approves the model authorisation.
extension LioMenuService {
    static let preview = LioMenuService { _ in
        try await Task.sleep(for: .milliseconds(500))
        return .sample
    }
}

extension LioMenuReading {
    static let sample = LioMenuReading(dishes: [
        LioMenuDish(
            id: "1", nameZH: "宫保鸡丁", nameEN: "Kung Pao Chicken",
            summaryEN: "Diced chicken stir-fried with peanuts and dried chili; sweet, sour and a little numbing.",
            summaryZH: "鸡丁与花生、干辣椒同炒，酸甜微麻。",
            ingredientsEN: "Chicken, peanuts, dried chili, Sichuan pepper, spring onion",
            ingredientsZH: "鸡肉、花生、干辣椒、花椒、葱",
            methodEN: "Stir-fried", methodZH: "爆炒",
            portionEN: "Shared plate, about 2 people", portionZH: "一盘，约 2 人份",
            spice: .medium, contains: [.poultry: .likely, .peanut: .likely, .soy: .likely, .alcohol: .possible],
            priceText: "¥38"),
        LioMenuDish(
            id: "2", nameZH: "麻婆豆腐", nameEN: "Mapo Tofu",
            summaryEN: "Soft tofu in a spicy, numbing bean sauce, usually with minced pork.",
            summaryZH: "嫩豆腐配麻辣豆瓣酱，通常有猪肉末。",
            ingredientsEN: "Tofu, minced pork, chili bean paste, Sichuan pepper",
            ingredientsZH: "豆腐、猪肉末、豆瓣酱、花椒",
            methodEN: "Braised", methodZH: "烧",
            portionEN: "Shared bowl, 2–3 people", portionZH: "一碗，约 2–3 人份",
            spice: .hot, contains: [.pork: .likely, .soy: .likely],
            priceText: "¥26"),
        LioMenuDish(
            id: "3", nameZH: "西红柿炒鸡蛋", nameEN: "Tomato and Egg Stir-fry",
            summaryEN: "Scrambled egg with tomato in a light sweet-sour sauce. A home-style favourite.",
            summaryZH: "番茄炒鸡蛋，酸甜家常。",
            ingredientsEN: "Tomato, egg, spring onion", ingredientsZH: "番茄、鸡蛋、葱",
            methodEN: "Stir-fried", methodZH: "炒",
            portionEN: "Shared plate, 1–2 people", portionZH: "一盘，约 1–2 人份",
            spice: .notSpicy, contains: [.egg: .likely],
            priceText: "¥22"),
        LioMenuDish(
            id: "4", nameZH: "清炒时蔬", nameEN: "Stir-fried Seasonal Greens",
            summaryEN: "Whatever green vegetable is in season, quickly fried with garlic.",
            summaryZH: "当季青菜，蒜蓉清炒。",
            ingredientsEN: "Seasonal greens, garlic", ingredientsZH: "时令青菜、蒜",
            methodEN: "Stir-fried", methodZH: "清炒",
            portionEN: "Shared plate, 2 people", portionZH: "一盘，约 2 人份",
            spice: .notSpicy, contains: [.animalBroth: .possible],
            priceText: "¥18"),
        LioMenuDish(
            id: "5", nameZH: nil, nameEN: "Couldn't read this line",
            summaryEN: "", summaryZH: "", ingredientsEN: "", ingredientsZH: "", methodEN: "", methodZH: "",
            portionEN: "", portionZH: "", spice: nil, contains: [:], priceText: "¥4?"),
        LioMenuDish(
            id: "6", nameZH: "蛋炒饭", nameEN: "Egg Fried Rice",
            summaryEN: "Rice fried with egg and spring onion. Good with spicy dishes.",
            summaryZH: "鸡蛋葱花炒饭，适合配辣菜。",
            ingredientsEN: "Rice, egg, spring onion", ingredientsZH: "米饭、鸡蛋、葱",
            methodEN: "Fried", methodZH: "炒",
            portionEN: "One bowl, 1 person", portionZH: "一碗，1 人份",
            spice: .notSpicy, contains: [.egg: .likely, .soy: .possible],
            priceText: "¥15"),
    ], isSample: true)

    /// Memory rows the preview reads instead of the user's saved memory.
    static let sampleMemory = [LioMenuDietNote(slot: "diet.spicy", text: "不吃辣")]
}
#endif
