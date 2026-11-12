#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioSessionRecoveryFixture: View {
    let shell: ShellState
    @State private var offline = false
    @State private var retries = 0
    @State private var signedOut = false

    var body: some View {
        VStack(spacing: 0) {
            if signedOut {
                Text("Explicit sign-out callback")
                    .accessibilityIdentifier("synthetic.recovery.signedout")
            } else {
                LioSessionRecoveryView(language: shell.language.lio, showsRetry: offline,
                                       retry: { retries += 1; offline = false },
                                       signOut: { signedOut = true })
            }
            HStack {
                Button("Show connection problem") { offline = true }
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("synthetic.recovery.offline")
                Text(String(retries)).accessibilityIdentifier("synthetic.recovery.retry-count")
            }
            .font(.body)
            .foregroundStyle(LioTheme.ink)
            .tint(LioTheme.vermilion)
            .padding(LioTheme.Spacing.sm)
            .background(LioTheme.surface)
        }
    }
}
#endif
