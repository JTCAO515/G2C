// Generated simulator project only. Sample rates (ECB-shaped, fixed); nothing is fetched or sent.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
private struct LioCurrencyFixture: View {
    let chinese: Bool
    let dark: Bool

    var body: some View {
        NavigationStack {
            LioCurrencyView(language: chinese ? .chinese : .english, load: LioCurrencyRates.fixture)
        }
        .preferredColorScheme(dark ? .dark : .light)
    }
}
#endif
