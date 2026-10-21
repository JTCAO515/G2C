import Foundation
import SwiftUI
import Textual

/// Overrides Textual's network-fetching defaults for both image and emoji URLs.
struct BlockedAttachments: AttachmentLoader {
    func attachment(for url: URL, text: String, environment: ColorEnvironmentValues) async throws -> BlockedAttachment {
        BlockedAttachment(description: text.isEmpty ? "[图片已阻止 / Image blocked]" : "[\(text) · image blocked]")
    }
}
struct BlockedAttachment: Textual.Attachment {
    let description: String
    var body: some View { Text(description).font(.caption) }
    func sizeThatFits(_ proposal: ProposedViewSize, in environment: TextEnvironmentValues) -> CGSize {
        CGSize(width: min(proposal.width ?? 180, 180), height: 36)
    }
}
