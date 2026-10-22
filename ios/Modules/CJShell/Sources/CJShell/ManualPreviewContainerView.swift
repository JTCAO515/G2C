#if os(iOS)
import SwiftUI
import CJManualPreviewClient

struct ManualPreviewContainerView: View {
    let host: TripContainerHost
    let entry: ManualPreviewEntry
    let language: ShellLanguage
    @Environment(\.dismiss) private var dismiss
    @State private var confirmDiscard = false
    var body: some View {
        NavigationStack {
            Group {
                if let editor = host.manualEditor(for: entry) {
                    ManualPreviewView(editor: editor, language: language == .english ? .english : .chinese)
                } else {
                    Text(language.text("The original selection is unavailable. Return to Trip selection.", "原选择已不可用，请返回行程选择。"))
                        .padding()
                }
            }
            .navigationTitle(language.text("Local Trip draft", "本地行程草稿"))
            .toolbar { ToolbarItem(placement: .confirmationAction) {
                Button(language.text("Close", "关闭"), action: requestClose)
            }}
            .confirmationDialog(language.text("Discard this local draft?", "放弃此本地草稿？"), isPresented: $confirmDiscard, titleVisibility: .visible) {
                Button(language.text("Discard draft", "放弃草稿"), role: .destructive, action: leave)
                Button(language.text("Keep editing", "继续编辑"), role: .cancel) {}
            } message: {
                Text(language.text("The preview has not saved any changes. Closing discards only this in-memory draft.", "预览没有保存任何修改。关闭仅放弃此内存草稿。"))
            }
        }
        .interactiveDismissDisabled(true)
        .onDisappear { host.retireManualPreview(entry) }
    }
    private func requestClose() {
        guard host.manualPreviewIdentity == nil || host.manualPreviewIdentity == entry.id else { return }
        guard let editor = host.manualEditor(for: entry) else { leave(); return }
        // A failed source read is not evidence that the draft was empty.
        guard let display = editor.display() else { confirmDiscard = true; return }
        let hasIntent = display.titleSelected || !display.selectedIDs.isEmpty || !display.textUpdates.isEmpty
            || display.order != display.original.document.items.map(\.id)
        if hasIntent { confirmDiscard = true } else { leave() }
    }
    private func leave() {
        guard host.manualPreviewIdentity == nil || host.manualPreviewIdentity == entry.id else { return }
        host.retireManualPreview(entry)
        dismiss()
    }
}
#endif
