#if os(iOS)
import SwiftUI
import UIKit

enum LioLocalAddressResult {
    case address(String)
    case permissionDenied
    case offline
    case unavailable
}

struct LioLocalAddressView: View {
    let language: LioLanguage
    let resolve: @MainActor () async -> LioLocalAddressResult
    @State private var request: UUID?
    @State private var outcome: LioLocalAddressResult?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let outcome {
                    switch outcome {
                    case .address(let address):
                        Text(address)
                            .font(.largeTitle.bold())
                            .accessibilityIdentifier("lio.support.location.address")
                        Button {
                            UIPasteboard.general.string = address
                        } label: {
                            Label(language.text("Copy address", "复制地址"), systemImage: "doc.on.doc")
                                .foregroundStyle(LioTheme.ink)
                                .frame(minHeight: 44)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("lio.support.location.copy")
                    case .permissionDenied:
                        message(language.text("Location access is off. You can still use the help cards.",
                                              "定位权限未开启。你仍可以使用求助卡片。"))
                    case .offline:
                        message(language.text("Connect to the internet to look up your address.",
                                              "请联网查询当前位置的中文地址。"))
                    case .unavailable:
                        message(language.text("Your address couldn't be found. Try again.",
                                              "暂时查不到当前位置的地址，请重试。"))
                    }
                }
                if request != nil {
                    ProgressView(language.text("Finding your address…", "正在查询地址…"))
                }
                Button {
                    outcome = nil
                    request = UUID()
                } label: {
                    Label(language.text("Find my address", "查询我的地址"), systemImage: "location")
                        .foregroundStyle(LioTheme.ink)
                        .frame(minHeight: 44)
                        .padding(.horizontal, 14)
                        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .disabled(request != nil)
                .accessibilityIdentifier("lio.support.location.lookup")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Where Am I?", "我在哪"))
        .navigationBarTitleDisplayMode(.inline)
        .task(id: request) {
            guard request != nil else { return }
            let result = await resolve()
            guard !Task.isCancelled else { return }
            outcome = result
            request = nil
        }
    }

    private func message(_ text: String) -> some View {
        Text(text)
            .foregroundStyle(LioTheme.inkSecondary)
            .accessibilityIdentifier("lio.support.location.problem")
    }
}
#if DEBUG
#Preview {
    NavigationStack {
        LioLocalAddressView(language: .english) {
            .address("北京市东城区景山前街4号")
        }
    }
}
#endif
#endif
