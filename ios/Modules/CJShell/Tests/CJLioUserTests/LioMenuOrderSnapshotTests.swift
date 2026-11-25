#if os(iOS) && DEBUG
import SwiftUI
import Testing
import UIKit
@testable import CJLioUser

/// Renders the three menu-ordering screens with sample data. Always renders; writes PNGs only when
/// `LIO_MENU_SHOTS_DIR` is set (pass `TEST_RUNNER_LIO_MENU_SHOTS_DIR` to xcodebuild).
@MainActor struct LioMenuOrderSnapshotTests {
    private func shot(_ name: String, _ view: some View) throws {
        let renderer = ImageRenderer(content: view.frame(width: 393).background(LioTheme.paper))
        renderer.scale = 3
        let image = try #require(renderer.uiImage)
        #expect(image.size.height > 200)
        guard let folder = ProcessInfo.processInfo.environment["LIO_MENU_SHOTS_DIR"] else { return }
        try #require(image.pngData()).write(to: URL(fileURLWithPath: folder).appendingPathComponent(name + ".png"))
    }

    @Test func rendersIntroResultsAndCardInBothLanguages() throws {
        let needs: [LioDietaryNeed] = [.noSpicy, .peanut]
        let spicyMemory = LioMenuMemory.noSpicySource(LioMenuReading.sampleMemory)
        var order = LioMenuOrder()
        let reading = LioMenuReading.sample
        for dish in reading.dishes where ["宫保鸡丁", "西红柿炒鸡蛋", "蛋炒饭"].contains(dish.nameZH ?? "") {
            order.add(dish)
        }
        order.add(reading.dishes[5])
        for note in LioMenuNote.suggested(for: needs) { order.toggle(note) }
        order.toggle(.need(.noCoriander))
        for language in [LioLanguage.chinese, .english] {
            let suffix = language == .chinese ? "zh" : "en"
            try shot("1-intro-\(suffix)", LioMenuIntro(language: language, needs: .constant(needs), spicyMemory: spicyMemory) {
                // ImageRenderer cannot draw PhotosPicker; the same labels stand in for the two buttons.
                HStack(spacing: LioTheme.Spacing.sm) {
                    Label(language.text("Photograph menu", "拍菜单"), systemImage: "camera")
                        .foregroundStyle(LioTheme.onVermilion)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(LioTheme.vermilion, in: Capsule())
                    Label(language.text("Choose photo", "从相册选"), systemImage: "photo.on.rectangle")
                        .foregroundStyle(LioTheme.vermilion)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(LioTheme.surfaceSunken, in: Capsule())
                }
            }.padding(18))
            try shot("2-dishes-\(suffix)", LioMenuResults(language: language, reading: reading,
                                                          restrictions: needs,
                                                          order: .constant(order)).padding(18))
            try shot("3-card-\(suffix)", LioMenuCardContent(language: language, card: order.card(in: reading),
                                                            order: .constant(order)).padding(24))
        }
    }
}
#endif
