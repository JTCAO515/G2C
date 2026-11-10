#if os(iOS)
import CJMessageHTTP
import SwiftUI

struct LioChatHistoryView: View {
    let library: LioChatLibrary
    let language: LioLanguage
    let currentID: Data?
    let canSwitch: Bool
    let select: (LioChatSession) -> Void

    @State private var state = LoadState.loading
    @State private var attempt = 0

    private enum LoadState {
        case loading, loaded([LioChatSession]), failed
    }

    var body: some View {
        List {
            switch state {
            case .loading:
                ProgressView()
            case .loaded(let chats) where chats.isEmpty:
                Text(language.text("Your conversations will appear here.", "你的对话会出现在这里。"))
            case .loaded(let chats):
                ForEach(chats) { chat in
                    Button { select(chat) } label: {
                        HStack {
                            Text(title(for: chat))
                            Spacer()
                            if chat.id == currentID {
                                Image(systemName: "checkmark").accessibilityHidden(true)
                            }
                        }
                    }
                    .disabled(!canSwitch)
                    .accessibilityIdentifier("lio.chat.history.row")
                    .accessibilityAddTraits(chat.id == currentID ? .isSelected : [])
                }
            case .failed:
                Text(language.text("Couldn’t show your conversations.", "暂时看不到对话。"))
                Button(language.text("Try again", "再试一次")) { attempt += 1 }
            }
        }
        .navigationTitle(language.text("Chat history", "历史对话"))
        .task(id: attempt) {
            state = .loading
            do {
                let chats = try await library.history()
                try Task.checkCancellation()
                state = .loaded(chats)
            } catch is CancellationError {
                return
            } catch {
                state = .failed
            }
        }
    }

    private func title(for chat: LioChatSession) -> String {
        let text = chat.title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, LioPublicDisplay.permitsText(text) else {
            return language.text("Untitled conversation", "未命名对话")
        }
        return text
    }
}
#endif
