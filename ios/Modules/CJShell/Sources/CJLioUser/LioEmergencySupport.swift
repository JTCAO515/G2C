#if os(iOS)
import SwiftUI

public struct LioEmergencySupportButton: View {
    private let language: LioLanguage
    private let standalone: Bool
    private let action: () -> Void

    public init(language: LioLanguage, standalone: Bool = true, action: @escaping () -> Void) {
        self.language = language
        self.standalone = standalone
        self.action = action
    }

    public var body: some View {
        Group {
            if standalone {
                button.lioFloatingSurface(Circle(), interactive: true)
            } else {
                button
            }
        }
    }

    private var button: some View {
        Button(action: action) {
            Image(systemName: "sos.circle")
                .font(.body.weight(.semibold))
                .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                .foregroundStyle(LioTheme.danger)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(language.text("Emergency help", "紧急求助"))
        .accessibilityIdentifier("lio.support.sos")
    }
}

public struct LioEmergencySupportSheet: View {
    private let language: LioLanguage
    private let draftStorage: LocalSupportDraftStorage?
    @Environment(\.dismiss) private var dismiss

    public init(language: LioLanguage, draftStorage: LocalSupportDraftStorage? = nil) {
        self.language = language
        self.draftStorage = draftStorage
    }

    public var body: some View {
        NavigationStack {
            LioLocalSupportView(language: language, draftStorage: draftStorage)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button(language.text("Close", "关闭")) { dismiss() }
                    }
                }
        }
    }
}
public extension View {
    func lioEmergencySupportFallback(language: LioLanguage, enabled: Bool,
                                     draftStorage: LocalSupportDraftStorage? = nil) -> some View {
        modifier(LioEmergencySupportFallback(language: language, enabled: enabled, draftStorage: draftStorage))
    }
}

private struct LioEmergencySupportFallback: ViewModifier {
    let language: LioLanguage
    let enabled: Bool
    let draftStorage: LocalSupportDraftStorage?
    @State private var showSupport = false

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .topTrailing) {
                if enabled {
                    LioEmergencySupportButton(language: language) { showSupport = true }
                        .padding(16)
                }
            }
            .sheet(isPresented: $showSupport) {
                LioEmergencySupportSheet(language: language, draftStorage: draftStorage)
            }
    }
}
#endif
