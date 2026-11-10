// App source used only by the generated simulator acceptance project.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioScrollFixture: View {
    let shell: ShellState
    @State private var sections = AsyncStream<Void>.makeStream()

    var body: some View {
        let stream = sections.stream
        let arguments = ProcessInfo.processInfo.arguments
        let hiddenText: String? = if arguments.contains("--lio-display-guard-markdown") {
            " 查**询**后，暂时没有预报。"
        } else if arguments.contains("--lio-display-guard-host") {
            " [Forecast](https://%EF%BD%81pi-beta.go2china.space%E3%80%82/)"
        } else if arguments.contains("--lio-display-guard-wrapped-host") {
            " 请看（https://%61pi-beta.go2china.space）天气"
        } else if arguments.contains("--lio-display-guard") {
            " 我查询了高德天气接口，暂时没有预报。"
        } else {
            nil
        }
        LioHome(language: shell.language.lio, service: LioService { _ in
            AsyncStream { output in
                let task = Task {
                    defer { output.finish() }
                    output.yield(.text("Here is the first part."))
                    output.yield(.source(.init(id: "scroll-source", title: "Sample travel guide", url: nil)))
                    var next = stream.makeAsyncIterator()
                    guard await next.next() != nil else { return }
                    if let hiddenText {
                        output.yield(.text(hiddenText))
                        output.yield(.finished)
                        return
                    }
                    output.yield(.text("\n\nLong section." + String(repeating: "\n\nMore travel details are shown here.", count: 24)))
                    guard await next.next() != nil else { return }
                    output.yield(.text("\n\nEnd of the reply."))
                    output.yield(.finished)
                }
                output.onTermination = { _ in task.cancel() }
            }
        }, isDemo: true) {
            LioMenuSettings(shell: shell)
        }
        .overlay(alignment: .topTrailing) {
            Button("Next section") { sections.continuation.yield(()) }
                .padding(12)
        }
    }
}
#endif
