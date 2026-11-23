#if os(iOS) && DEBUG
import SwiftUI

struct LioLocalSupportReplyPreview: View {
    let language: LioLanguage
    let reply: Data
    let conversationID: String
    let messageID: String
    @State private var showingSupport = false

    private var canOpenSupport: Bool {
        do {
            let action = try JSONDecoder().decode(LioLocalSupportAction.self, from: reply)
            return try action.opensSupport(conversationID: conversationID, messageID: messageID)
        } catch {
            // Keep the answer visible when its separate action cannot be verified.
            return false
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: LioTheme.Spacing.sm) {
            Text(language.text("110 is the police emergency number.", "110 是报警电话。"))
            if canOpenSupport {
                Button {
                    showingSupport = true
                } label: {
                    Label(language.text("Open Local Support", "打开本地协助"), systemImage: "sos.circle")
                        .frame(minWidth: 44, minHeight: 46)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.reply.open-local-support")
            }
        }
        .padding(LioTheme.Spacing.md)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .sheet(isPresented: $showingSupport) {
            LioEmergencySupportSheet(language: language)
        }
    }
}

private let emergencyReply = Data("""
{"version":"LIO-local-support-action.1","conversation_id":"sample-chat","message_id":"sample-answer","action":"open_local_support"}
""".utf8)

#Preview {
    LioLocalSupportReplyPreview(language: .english, reply: emergencyReply,
                                conversationID: "sample-chat", messageID: "sample-answer")
}

#Preview {
    LioLocalSupportReplyPreview(language: .chinese, reply: emergencyReply,
                                conversationID: "sample-chat", messageID: "other-answer")
}
#endif
