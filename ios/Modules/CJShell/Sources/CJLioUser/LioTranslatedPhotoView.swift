#if os(iOS)
import SwiftUI
import UIKit

struct LioTranslatedPhotoView: View {
    private enum Display: Hashable {
        case translated, original, lines
    }

    let language: LioLanguage
    let photo: LioTranslatedPhoto
    let lines: [LioImageTranslationLine]
    @State private var display = Display.translated

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(spacing: 6) {
                    selector(.translated, language.text("Translated", "译图"))
                    selector(.original, language.text("Original", "原图"))
                    selector(.lines, language.text("Line by line", "逐行对照"))
                }
                .accessibilityIdentifier("lio.translation.photo-layout.display")

                switch display {
                case .translated:
                    picture(photo.translated, label: language.text("Translated photo", "带译文的照片"))
                case .original:
                    picture(photo.original, label: language.text("Original photo", "原始照片"))
                case .lines:
                    ForEach(lines) { line in
                        VStack(alignment: .leading, spacing: 5) {
                            Text(line.original)
                            Text(line.translated).font(.body.weight(.semibold))
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                        .accessibilityElement(children: .combine)
                    }
                }
            }
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Photo Translation", "图片翻译"))
        .navigationBarTitleDisplayMode(.inline)
    }

    private func selector(_ choice: Display, _ title: String) -> some View {
        Button { display = choice } label: {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 44)
                .background(display == choice ? LioTheme.surfaceSunken : LioTheme.surface,
                            in: RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(display == choice ? .isSelected : [])
    }

    private func picture(_ bytes: Data, label: String) -> some View {
        Group {
            if let image = UIImage(data: bytes) {
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .accessibilityLabel(label)
                    .accessibilityIdentifier("lio.translation.photo-layout.image")
            } else {
                Text(language.text("This image couldn’t be displayed.", "无法显示这张图片。"))
            }
        }
    }
}

#if DEBUG
extension LioTranslatedPhoto {
    @MainActor static func fixture() -> LioTranslatedPhoto? {
        func sample(_ first: String, _ second: String) -> Data? {
            let format = UIGraphicsImageRendererFormat()
            format.scale = 1
            let renderer = UIGraphicsImageRenderer(size: CGSize(width: 680, height: 360), format: format)
            return renderer.image { context in
                UIColor(red: 0.94, green: 0.89, blue: 0.8, alpha: 1).setFill()
                context.fill(CGRect(x: 0, y: 0, width: 680, height: 360))
                let style: [NSAttributedString.Key: Any] = [
                    .font: UIFont.systemFont(ofSize: 60, weight: .semibold),
                    .foregroundColor: UIColor(red: 0.22, green: 0.1, blue: 0.08, alpha: 1),
                ]
                (first as NSString).draw(at: CGPoint(x: 50, y: 70), withAttributes: style)
                (second as NSString).draw(at: CGPoint(x: 50, y: 198), withAttributes: style)
            }.jpegData(compressionQuality: 0.8)
        }

        guard let original = sample("茶", "咖啡"), let translated = sample("Tea", "Coffee") else { return nil }
        return LioTranslatedPhoto(original: original, translated: translated)
    }
}
#endif
#endif
