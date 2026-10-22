import Foundation
import SwiftUI

public enum ManualPreviewLanguage: Sendable { case english, chinese }

/// Feature-local component; host supplies a current formal-detail editor and owns navigation.
@MainActor public struct ManualPreviewView: View {
    private let editor: PreviewEditor
    private let language: ManualPreviewLanguage
    @State private var inputError = false
    public init(editor: PreviewEditor, language: ManualPreviewLanguage) {
        self.editor = editor; self.language = language
    }
    private func text(_ en: String, _ zh: String) -> String { language == .chinese ? zh : en }
    private func change(_ action: () throws -> Void) {
        do { try action(); inputError = false } catch { inputError = true }
    }
    public var body: some View {
        Group {
            if let display = editor.display() {
                Form {
                    Section {
                        Text(text("Local draft · not saved", "本地草稿 · 尚未保存"))
                        Text(text("Protection unknown. Preview does not verify feasibility or fixed items.", "保护状态未知。预览不代表可行性或固定事项已核实。"))
                        Text(text("Base version: ", "原版本：") + String(display.original.version))
                    }
                    Section(text("Selected scope", "选定范围")) {
                        Toggle(text("Edit title", "修改标题"), isOn: Binding(get: { display.titleSelected }, set: { value in change { try editor.selectTitle(value) } }))
                        if display.titleSelected {
                            TextField(text("Title", "标题"), text: Binding(get: { display.title }, set: { value in change { try editor.setTitle(value) } }), axis: .vertical)
                        }
                        ForEach(display.order, id: \.self) { id in
                            if let item = display.original.document.items.first(where: { $0.id == id }) {
                                let selected = display.selectedIDs.contains(id)
                                Toggle(item.text, isOn: Binding(get: { selected }, set: { value in change { try editor.selectItem(id, selected: value) } }))
                                if selected {
                                    TextField(text("Item text", "条目内容"), text: Binding(get: { display.textUpdates[id] ?? item.text }, set: { value in change { try editor.setText(value, for: id) } }), axis: .vertical)
                                }
                            }
                        }
                        .onMove { from, to in
                            var order = display.order; order.move(fromOffsets: from, toOffset: to)
                            change { try editor.setOrder(order) }
                        }
                    }
                    Section {
                        Button(text("Preview changes", "预览修改")) {
                            change {
                                let work = try editor.preparePreview()
                                Task { await editor.perform(work) }
                            }
                        }
                        .disabled(display.status == .loading)
                        if display.status == .loading {
                            ProgressView(text("Calculating preview", "正在计算预览"))
                            Button(text("Cancel preview", "取消预览")) { editor.cancelPreview() }
                        }
                        Text(statusText(display.status))
                        if inputError { Text(text("This change is unavailable or outside the selected scope. Your draft is retained.", "该修改不可用或超出选定范围，草稿已保留。")) }
                    }
                    if let preview = display.preview {
                        Section(text("Server changes · read only", "服务器差异 · 只读")) {
                            if preview.diff.isEmpty { Text(text("No changes", "没有变化")) }
                            ForEach(Array(preview.diff.enumerated()), id: \.offset) { _, item in
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(item.path.joined(separator: " / ")).font(.headline)
                                    Text(text("Before: ", "修改前：") + value(item.before_utf8_base64))
                                    Text(text("After: ", "修改后：") + value(item.after_utf8_base64))
                                }.textSelection(.enabled)
                            }
                            Text(text("Preview only. Saving and confirmation are unavailable.", "仅预览。保存与确认尚未开放。"))
                        }
                    }
                }
                #if os(iOS)
                .toolbar { EditButton() }
                #endif
            } else {
                Text(text("This source is no longer current. Return to the Trip selection.", "原来源已失效，请返回行程选择。"))
            }
        }
        .environment(\.locale, Locale(identifier: language == .chinese ? "zh-Hans" : "en"))
        .onDisappear { editor.retire() }
    }
    private func value(_ base64: String) -> String {
        Data(base64Encoded: base64).flatMap { String(data: $0, encoding: .utf8) } ?? text("Invalid value", "无效值")
    }
    private func statusText(_ status: PreviewStatus) -> String {
        switch status {
        case .editing: text("Draft retained in memory.", "草稿保留在内存中。")
        case .loading: text("Read-only computation; no save.", "只读计算，不会保存。")
        case .local: text("Local preview ready; not saved.", "本地预览就绪，尚未保存。")
        case .conflict: text("The base changed. Draft retained; choose a new base explicitly.", "原版本已变化。草稿已保留，请明确选择新基准。")
        case .unknown: text("Preview unknown or unavailable. Draft retained; no automatic retry.", "预览结果未知或不可用。草稿已保留，不会自动重试。")
        case .invalidResponse: text("Preview response rejected. Draft retained.", "预览响应已拒绝，草稿已保留。")
        case .unavailable: text("Preview unavailable. Draft retained.", "预览不可用，草稿已保留。")
        }
    }
}
