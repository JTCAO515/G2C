#if os(iOS)
import CJRunClient
import SwiftUI
import UIKit

/// The one "show the driver" card: the Chinese name large, the Chinese address under it, the English name small.
/// It takes plain text, so a station or airport without coordinates can use it without a made-up location.
/// The screen stays awake while it is shown. Taxi, trip, hotel, roadbook and transport cards all present this view.
struct LioDriverSign: View {
    let language: LioLanguage
    let nameZH: String
    var nameEN: String?
    var addressZH: String?
    /// An optional Chinese request above the name, such as 请送我到这个火车站.
    var requestZH: String?
    /// Accessibility identifiers are `<prefix>.request`, `<prefix>.name`, `<prefix>.address` and `<prefix>.done`.
    var identifierPrefix = "lio.driver"
    @Environment(\.dismiss) private var dismiss
    @State private var priorIdleTimer: Bool?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let requestZH, !requestZH.isEmpty {
                        Text(requestZH).font(.title3.weight(.semibold)).foregroundStyle(LioTheme.inkSecondary)
                            .accessibilityIdentifier(identifierPrefix + ".request")
                    }
                    Text(nameZH).font(LioTheme.display(.largeTitle).weight(.bold))
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier(identifierPrefix + ".name")
                    if let addressZH, !addressZH.isEmpty {
                        Text(addressZH).font(.title2.weight(.semibold))
                            .accessibilityIdentifier(identifierPrefix + ".address")
                    }
                    if let nameEN, !nameEN.isEmpty, nameEN != nameZH {
                        Text(nameEN).font(.body).foregroundStyle(LioTheme.inkSecondary)
                    }
                }
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(24)
            }
            .background(LioTheme.paper)
            .foregroundStyle(LioTheme.ink)
            .navigationTitle(language.text("Show the driver", "给司机看"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    // Navigation-bar text does not follow Dynamic Type; this label does.
                    Button { dismiss() } label: {
                        RunReadableText(text: language.text("Close", "关闭"), color: LioTheme.vermilion).fixedSize()
                            .frame(minHeight: 44)
                    }
                    .accessibilityLabel(language.text("Close", "关闭"))
                    .accessibilityIdentifier(identifierPrefix + ".done")
                }
            }
        }
        .tint(LioTheme.vermilion)
        .onAppear {
            guard priorIdleTimer == nil else { return }
            priorIdleTimer = UIApplication.shared.isIdleTimerDisabled
            UIApplication.shared.isIdleTimerDisabled = true
        }
        .onDisappear {
            if let priorIdleTimer {
                UIApplication.shared.isIdleTimerDisabled = priorIdleTimer
                self.priorIdleTimer = nil
            }
        }
    }
}
#endif
