#if os(iOS) && DEBUG
import SwiftUI

struct LioEmergencyChatPreview: View {
    let language: LioLanguage
    @State private var presentsSupport = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(language.text("Open Local Support for emergency numbers and help.", "打开本地协助查看紧急电话和求助方式。"))
            Button { presentsSupport = true } label: {
                Label(language.text("Open Local Support", "打开本地协助"), systemImage: "sos.circle")
                    .frame(minHeight: 44)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("lio.chat.preview.emergency-support")
        }
        .padding(.horizontal, 16)
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .sheet(isPresented: $presentsSupport) {
            NavigationStack {
                LioLocalSupportView(language: language, directory: try? LocalSupportDirectory.bundled())
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button(language.text("Close", "关闭")) { presentsSupport = false }
                                .frame(minWidth: 44, minHeight: 44)
                        }
                    }
            }
        }
    }
}
#endif
