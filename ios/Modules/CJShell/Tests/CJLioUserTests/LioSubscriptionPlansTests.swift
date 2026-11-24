import Foundation
import Testing
@testable import CJLioUser

/// #1452: the plans page is a preview only (JT 2026-11-24): three monthly prices, no purchase, no StoreKit,
/// and no "unlimited" or service-hours promises.
@Suite struct LioSubscriptionPlansTests {
    @Test func threePlansWithTheConfirmedPrices() {
        let plans = LioSubscriptionPlans.plans
        #expect(plans.map(\.nameEN) == ["Explorer", "Traveler", "Concierge"])
        #expect(plans.map(\.nameZH) == ["探索", "畅游", "尊享"])
        #expect(plans.map(\.priceText) == ["$9.99", "$19.99", "$49.99"])
        #expect(plans.filter(\.highlighted).map(\.id) == ["traveler"])
    }

    @Test func benefitsMakeNoUnlimitedOrServiceHoursPromise() {
        for benefit in LioSubscriptionPlans.benefits {
            #expect(benefit.values.count == LioSubscriptionPlans.plans.count)
            for case let .text(en, zh) in benefit.values {
                #expect(!en.localizedCaseInsensitiveContains("unlimited") && !zh.contains("不限"))
                #expect(!en.localizedCaseInsensitiveContains("hours") && !zh.contains("工作时间"))
            }
        }
        let human = LioSubscriptionPlans.benefits.first { $0.id == "human" }
        #expect(human?.values.last == .text(en: "Planned", zh: "规划中"))
    }

    @Test func noModuleSourceUsesStoreKit() throws {
        let sources = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../Sources").standardizedFileURL
        let files = try #require(FileManager.default.enumerator(at: sources, includingPropertiesForKeys: nil))
        var checked = 0
        for case let file as URL in files where file.pathExtension == "swift" {
            let text = try String(contentsOf: file, encoding: .utf8)
            #expect(!text.contains("import StoreKit"), "\(file.lastPathComponent)")
            #expect(!text.contains("Product.purchase") && !text.contains("SKPaymentQueue"), "\(file.lastPathComponent)")
            checked += 1
        }
        #expect(checked > 100)
    }
}
