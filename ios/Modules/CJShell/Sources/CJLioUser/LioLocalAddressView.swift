#if os(iOS)
import CJRunClient
import SwiftUI
import UIKit

enum LioLocalAddressResult: Equatable {
    case address(String)
    case permissionDenied
    case offline
    case notEnabled
    case rateLimited
    case outcomeUnknown
    case unavailable
}

struct LioLocalAddressView: View {
    let language: LioLanguage
    let isCurrent: @MainActor () -> Bool
    let resolve: @MainActor () async -> LioLocalAddressResult
    @Environment(\.colorScheme) private var colorScheme
    @State private var request: UUID?
    @State private var outcome: LioLocalAddressResult?

    init(language: LioLanguage, isCurrent: @escaping @MainActor () -> Bool = { true },
         resolve: @escaping @MainActor () async -> LioLocalAddressResult) {
        self.language = language
        self.isCurrent = isCurrent
        self.resolve = resolve
    }

    private var title: String { language.text("Where Am I?", "我在哪") }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(language.text("Use your current location to find the address in Chinese.",
                                   "使用当前位置查看中文地址。"))
                    .foregroundStyle(LioTheme.inkSecondary)
                if isCurrent(), let result = outcome {
                    switch result {
                    case .address(let address):
                        Text(address)
                            .font(.largeTitle.bold())
                            .accessibilityIdentifier("lio.support.location.address")
                        Button {
                            guard isCurrent() else { outcome = nil; return }
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
                                              "联网后可查看当前位置的中文地址。"))
                    case .notEnabled:
                        message(language.text("Address lookup is unavailable for this account.",
                                              "当前账号暂不能查看中文地址。"))
                    case .rateLimited:
                        message(language.text("Too many lookups. Try again later.",
                                              "查看地址次数过多，请稍后再试。"))
                    case .outcomeUnknown:
                        message(language.text("The address couldn’t be confirmed. You can still use the help cards.",
                                              "未能确认当前位置的地址。你仍可以使用求助卡片。"))
                    case .unavailable:
                        message(language.text("Your address couldn't be found. Try again.",
                                              "暂时查不到当前位置的地址，请重试。"))
                    }
                }
                if request != nil {
                    ProgressView(language.text("Finding your address…", "正在查找地址…"))
                }
                Button {
                    guard isCurrent() else { outcome = nil; return }
                    outcome = nil
                    request = UUID()
                } label: {
                    Label(language.text("Find my address", "查看我的地址"), systemImage: "location")
                        .foregroundStyle(LioTheme.ink)
                        .frame(minHeight: 44)
                        .padding(.horizontal, 14)
                        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.small))
                }
                .buttonStyle(.plain)
                .disabled(request != nil || outcome == .outcomeUnknown)
                .accessibilityIdentifier("lio.support.location.lookup")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .principal) {
                RunReadableText(text: title, style: .headline, color: LioTheme.ink)
                    .accessibilityAddTraits(.isHeader)
            }
        }
        .onDisappear {
            request = nil
            outcome = nil
        }
        .task(id: request) {
            guard request != nil else { return }
            let result = await resolve()
            guard !Task.isCancelled, isCurrent() else {
                outcome = nil
                request = nil
                return
            }
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
