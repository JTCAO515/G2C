import Foundation
import CJNeedsClient
import CJFeasibilityClient

/// Local presentation identity, never a network capability or save permission.
@MainActor public final class FeasibilityHostPresentation: Identifiable {
    public let id: UUID
    public let model: FeasibilityModel
    public let binding: FeasibilityBinding
    let snapshot: NeedsSchema.NeedsSnapshot
    let sourceEpoch: UUID
    let containerID: UUID
    init(id: UUID, model: FeasibilityModel, binding: FeasibilityBinding,
         snapshot: NeedsSchema.NeedsSnapshot, sourceEpoch: UUID, containerID: UUID) {
        self.id = id; self.model = model; self.binding = binding
        self.snapshot = snapshot; self.sourceEpoch = sourceEpoch; self.containerID = containerID
    }
}

#if os(iOS)
import SwiftUI

struct FeasibilityHostView: View {
    let host: NeedsContainerHost
    let entry: FeasibilityHostPresentation
    let language: ShellLanguage
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(language.text("Accepted source: ", "已读取来源：") + entry.binding.needsID)
            Text(language.text("Revision: ", "版本：") + String(entry.snapshot.version)).font(.caption)
            if let hash = entry.binding.acceptedContentSHA256 {
                Text("SHA256 " + hash).font(.caption).textSelection(.enabled)
            }
            FeasibilityView(model: entry.model, binding: entry.binding,
                language: language == .english ? .english : .chinese)
            Button(language.text("Close evaluation", "关闭评估")) {
                host.dismissFeasibility(id: entry.id)
            }.accessibilityIdentifier("needs.feasibility.close")
        }
        .onDisappear { host.dismissFeasibility(id: entry.id) }
    }
}
#endif
