import SwiftUI

public enum LioAppearance: String, CaseIterable, Sendable {
    case system, light, dark

    public static let preferenceKey = "lio.ui.appearance.v1"

    public var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }

    func title(_ language: LioLanguage) -> String {
        switch self {
        case .system: language.text("System", "跟随系统")
        case .light: language.text("Light", "浅色")
        case .dark: language.text("Dark", "深色")
        }
    }
}

public struct LioAppearancePicker: View {
    private let language: LioLanguage
    @AppStorage(LioAppearance.preferenceKey) private var appearance = LioAppearance.system

    public init(language: LioLanguage) {
        self.language = language
    }

    public var body: some View {
        Picker(language.text("Appearance", "外观"), selection: $appearance) {
            ForEach(LioAppearance.allCases, id: \.self) { choice in
                Text(choice.title(language)).tag(choice)
            }
        }
        .pickerStyle(.menu)
        .accessibilityIdentifier("lio.appearance")
    }
}
