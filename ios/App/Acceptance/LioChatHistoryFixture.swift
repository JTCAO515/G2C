// Local fixture only, used by the generated simulator acceptance project.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageHTTP

private struct LioChatHistoryFixture: View {
    let shell: ShellState
    let original: LioChatSession
    @State private var chats: [LioChatSession]

    init(shell: ShellState) {
        self.shell = shell
        let page = try! LioTimelineWire.decodePage(Data("""
            {"version":"LIO-timeline.1","conversation_id":"lio-dialogue-0123456789abcdef0123456789abcdef",
             "messages":[{"message_id":"sample-old","text":"An earlier question",
                          "answer":"An earlier reply.","status":"completed","sources":[]}],"next_before":null}
            """.utf8))
        let service = LioService(updates: { _ in
            AsyncStream { stream in
                stream.yield(LioTimelinePage(page))
                stream.finish()
            }
        }) { _ in AsyncStream { $0.finish() } }
        let original = LioChatSession(id: "fixture-original", title: "Earlier conversation", service: service)
        self.original = original
        _chats = State(initialValue: [original])
    }

    var body: some View {
        LioHome(language: shell.language.lio, service: original.service, isDemo: true,
                chatLibrary: LioChatLibrary(currentID: "fixture-original", history: { chats }, newChat: {
            let chat = LioChatSession(id: "fixture-new-\(chats.count)", title: "New conversation", service: .demo)
            chats.insert(chat, at: 0)
            return chat
        })) {
            LioLanguagePicker(shell: shell)
        }
    }
}
#endif
