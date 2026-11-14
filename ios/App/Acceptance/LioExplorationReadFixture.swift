// Generated simulator acceptance only. Frozen v4 fields plus explicit synthetic profile/notice.
#if DEBUG && G2C_LIO_APP && targetEnvironment(simulator)
import CJMessageHTTP
struct LioExplorationReadFixture: View {
    let chinese: Bool
    private let decoded: LioExplorationDisplay?
    @State private var draft: LioQuestionDraft
    @State private var sent = ""
    @State private var count = 0
    init(chinese: Bool) {
        self.chinese = chinese
        let samples = ["en": "eyJ2ZXJzaW9uIjoiTElPLXRpbWVsaW5lLjQiLCJjb252ZXJzYXRpb25faWQiOiJsaW8tZGlhbG9ndWUtYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWEiLCJtZXNzYWdlcyI6W3sibWVzc2FnZV9pZCI6ImV4cGxvcmUtZW4iLCJ0ZXh0IjoiSSB3b3VsZCBsaWtlIHRvIHZpc2l0IENoaW5hIiwiYW5zd2VyIjoiV2UgY2FuIHBsYW4gb25lIGNpdHkgaW4gdGhpcyB2ZXJzaW9uLlxuXG5XaGF0IHdvdWxkIHlvdSBtb3N0IGxpa2UgdG8gZXhwbG9yZT9cbkhpc3RvcnkgLyBGb29kIC8gTmF0dXJlXG5cbkJyaW5nIGEgcmFpbmNvYXQuXG5cbktlZXAgZXhwbG9yaW5nIC8gTWFrZSBhIHBsYW4gbm93Iiwic3RhdHVzIjoiY29tcGxldGVkIiwiZmFpbHVyZSI6bnVsbCwiYWN0aXZpdHkiOm51bGwsInNvdXJjZXMiOltdLCJ0cmlwIjpudWxsLCJtZW1vcnkiOm51bGwsInNlZ21lbnRzIjpbeyJwdXJwb3NlIjoiZGlyZWN0aW9uIiwidGV4dCI6IldlIGNhbiBwbGFuIG9uZSBjaXR5IGluIHRoaXMgdmVyc2lvbi4ifV0sInF1ZXN0aW9uX2dyb3VwcyI6W3siZmFjdG9yX2tleSI6ImludGVyZXN0cyIsInF1ZXN0aW9uIjoiV2hhdCB3b3VsZCB5b3UgbW9zdCBsaWtlIHRvIGV4cGxvcmU/IiwibXVsdGlwbGUiOnRydWUsIm9wdGlvbnMiOlt7ImlkIjoiaW50ZXJlc3RzLmhpc3RvcnkiLCJkaXNwbGF5X3RleHQiOiJIaXN0b3J5Iiwic2VuZF90ZXh0IjoiSW50ZXJlc3RzOiBIaXN0b3J5In0seyJpZCI6ImludGVyZXN0cy5mb29kIiwiZGlzcGxheV90ZXh0IjoiRm9vZCIsInNlbmRfdGV4dCI6IkludGVyZXN0czogRm9vZCJ9LHsiaWQiOiJpbnRlcmVzdHMubmF0dXJlIiwiZGlzcGxheV90ZXh0IjoiTmF0dXJlIiwic2VuZF90ZXh0IjoiSW50ZXJlc3RzOiBOYXR1cmUifV19XSwicHJvZmlsZSI6W3siZmFjdG9yX2tleSI6ImNpdHkiLCJkaXNwbGF5X3RleHQiOiJCZWlqaW5nIiwic3RhdGUiOiJrbm93biJ9LHsiZmFjdG9yX2tleSI6InBhY2UiLCJkaXNwbGF5X3RleHQiOiJBbiBlYXN5IHBhY2UiLCJzdGF0ZSI6ImluZmVycmVkIn1dLCJub3RpY2VzIjpbeyJpZCI6IndlYXRoZXIuMSIsInR5cGUiOiJ3ZWF0aGVyIiwic2V2ZXJpdHkiOiJpbmZvIiwiaXRlbV9pZHMiOltdLCJ0ZXh0IjoiQnJpbmcgYSByYWluY29hdC4iLCJzb3VyY2UiOnsidGl0bGUiOiJXZWF0aGVyIGd1aWRhbmNlIiwidXJsIjoiaHR0cHM6Ly9leGFtcGxlLm9yZy9ndWlkZSIsIm9ic2VydmVkX2F0IjoiMjAyNi0xMS0xNFQwMDowMDowMFoifX1dLCJleGl0cyI6W3siaWQiOiJjb250aW51ZV9yZWZpbmluZyIsImRpc3BsYXlfdGV4dCI6IktlZXAgZXhwbG9yaW5nIiwic2VuZF90ZXh0IjoiS2VlcCBleHBsb3JpbmcifSx7ImlkIjoicGxhbl9ub3ciLCJkaXNwbGF5X3RleHQiOiJNYWtlIGEgcGxhbiBub3ciLCJzZW5kX3RleHQiOiJNYWtlIGEgcGxhbiBub3cifV0sInByb2dyZXNzIjpudWxsfV0sIm5leHRfYmVmb3JlIjpudWxsfQ==",
"zh": "eyJ2ZXJzaW9uIjoiTElPLXRpbWVsaW5lLjQiLCJjb252ZXJzYXRpb25faWQiOiJsaW8tZGlhbG9ndWUtYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWEiLCJtZXNzYWdlcyI6W3sibWVzc2FnZV9pZCI6ImV4cGxvcmUtemgiLCJ0ZXh0Ijoi5oOz5Y675Lit5Zu9546p5Yeg5aSpIiwiYW5zd2VyIjoi6L+Z5LiA54mI5Y+v5Lul5YWI5a6J5o6S5LiA5bqn5Z+O5biC44CCXG5cbuabtOaDs+S9k+mqjOS7gOS5iO+8n1xu5Y6G5Y+yIC8g576O6aOfIC8g6Ieq54S2XG5cbuW4puS4gOS7tumbqOiho+OAglxuXG7nu6fnu63nu4bljJYgLyDnm7TmjqXlh7rmlrnmoYgiLCJzdGF0dXMiOiJjb21wbGV0ZWQiLCJmYWlsdXJlIjpudWxsLCJhY3Rpdml0eSI6bnVsbCwic291cmNlcyI6W10sInRyaXAiOm51bGwsIm1lbW9yeSI6bnVsbCwic2VnbWVudHMiOlt7InB1cnBvc2UiOiJkaXJlY3Rpb24iLCJ0ZXh0Ijoi6L+Z5LiA54mI5Y+v5Lul5YWI5a6J5o6S5LiA5bqn5Z+O5biC44CCIn1dLCJxdWVzdGlvbl9ncm91cHMiOlt7ImZhY3Rvcl9rZXkiOiJpbnRlcmVzdHMiLCJxdWVzdGlvbiI6IuabtOaDs+S9k+mqjOS7gOS5iO+8nyIsIm11bHRpcGxlIjp0cnVlLCJvcHRpb25zIjpbeyJpZCI6ImludGVyZXN0cy5oaXN0b3J5IiwiZGlzcGxheV90ZXh0Ijoi5Y6G5Y+yIiwic2VuZF90ZXh0Ijoi5YW06Laj77ya5Y6G5Y+yIn0seyJpZCI6ImludGVyZXN0cy5mb29kIiwiZGlzcGxheV90ZXh0Ijoi576O6aOfIiwic2VuZF90ZXh0Ijoi5YW06Laj77ya576O6aOfIn0seyJpZCI6ImludGVyZXN0cy5uYXR1cmUiLCJkaXNwbGF5X3RleHQiOiLoh6rnhLYiLCJzZW5kX3RleHQiOiLlhbTotqPvvJroh6rnhLYifV19XSwicHJvZmlsZSI6W3siZmFjdG9yX2tleSI6ImNpdHkiLCJkaXNwbGF5X3RleHQiOiLljJfkuqwiLCJzdGF0ZSI6Imtub3duIn0seyJmYWN0b3Jfa2V5IjoicGFjZSIsImRpc3BsYXlfdGV4dCI6IuaFouaFoumAmyIsInN0YXRlIjoiaW5mZXJyZWQifV0sIm5vdGljZXMiOlt7ImlkIjoid2VhdGhlci4xIiwidHlwZSI6IndlYXRoZXIiLCJzZXZlcml0eSI6ImluZm8iLCJpdGVtX2lkcyI6W10sInRleHQiOiLluKbkuIDku7bpm6jooaPjgIIiLCJzb3VyY2UiOnsidGl0bGUiOiJXZWF0aGVyIGd1aWRhbmNlIiwidXJsIjoiaHR0cHM6Ly9leGFtcGxlLm9yZy9ndWlkZSIsIm9ic2VydmVkX2F0IjoiMjAyNi0xMS0xNFQwMDowMDowMFoifX1dLCJleGl0cyI6W3siaWQiOiJjb250aW51ZV9yZWZpbmluZyIsImRpc3BsYXlfdGV4dCI6Iue7p+e7ree7huWMliIsInNlbmRfdGV4dCI6Iue7p+e7ree7huWMliJ9LHsiaWQiOiJwbGFuX25vdyIsImRpc3BsYXlfdGV4dCI6IuebtOaOpeWHuuaWueahiCIsInNlbmRfdGV4dCI6IuebtOaOpeWHuuaWueahiCJ9XSwicHJvZ3Jlc3MiOm51bGx9XSwibmV4dF9iZWZvcmUiOm51bGx9"]
        do {
            let data = Data(base64Encoded: samples[chinese ? "zh" : "en"]!)!
            guard let message = try LioExplorationWire.decodePage(data).messages.first else { throw LioExplorationDisplayFailure.unavailable }
            let display = try LioExplorationDisplay(message)
            decoded = display
            _draft = State(initialValue: display.draft())
        } catch {
            decoded = nil
            _draft = State(initialValue: LioQuestionDraft(messageID: "empty", questions: []))
        }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let decoded {
                    LioExplorationReplyView(presentation: decoded.presentation, questions: $draft,
                        language: chinese ? .chinese : .english, canSend: true) { text in sent = text; count += 1 }
                    Text(sent).accessibilityIdentifier("lio.exploration.sent")
                    Text("\(count)").accessibilityIdentifier("lio.exploration.send-count")
                } else { Text("Sample unavailable").accessibilityIdentifier("lio.exploration.fixture.unavailable") }
            }.padding(16)
        }
        .foregroundStyle(LioTheme.ink).lioPage()
        .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("--lio-read-dark-acceptance") ? .dark : .light)
    }
}
#endif
