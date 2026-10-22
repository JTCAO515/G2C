#if os(iOS)
import SwiftUI
import UIKit

/// The Agent brand image; never used for a personal account avatar.
struct BrandAvatar: View {
    let compact: Bool
    @ScaledMetric(relativeTo: .largeTitle) private var regularSize = 34.0
    @ScaledMetric(relativeTo: .title3) private var compactSize = 20.0

    private static let image: UIImage = {
        guard let url = Bundle.module.url(forResource: "BrandAvatar", withExtension: "png"),
              let image = UIImage(contentsOfFile: url.path) else {
            preconditionFailure("Missing or invalid packaged Agent brand image")
        }
        return image
    }()

    var body: some View {
        Image(uiImage: Self.image)
            .renderingMode(.original)
            .resizable()
            .scaledToFit()
            .frame(width: compact ? compactSize : regularSize,
                   height: compact ? compactSize : regularSize)
            .accessibilityHidden(true)
    }
}
#endif
