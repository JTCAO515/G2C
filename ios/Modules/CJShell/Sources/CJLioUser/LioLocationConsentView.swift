#if os(iOS)
import SwiftUI
import UIKit

/// #1748 (W4-4): what the traveller reads before choosing to use location. Wording approved by the coordinator
/// under JT's pre-authorisation (2026-11-26).
enum LioLocationConsentCopy {
    struct Point: Identifiable {
        let id: String
        let symbol: String
        let title: String
        let text: String
    }

    static func title(_ language: LioLanguage) -> String { language.text("Use your location?", "使用你的位置？") }

    static func points(_ language: LioLanguage) -> [Point] {
        [
            Point(id: "purpose", symbol: "mappin.and.ellipse", title: language.text("What for", "用途"),
                  text: language.text("To set your taxi pickup point and find places near you.",
                                      "用于设置打车起点、查找附近的地点。")),
            Point(id: "when", symbol: "clock", title: language.text("When", "何时"),
                  text: language.text("Only when you use these, while the app is open. Never in the background.",
                                      "只在你使用这两项、App 打开期间使用，不在后台使用。")),
            Point(id: "where", symbol: "arrow.up.forward.app", title: language.text("Where it goes", "去向"),
                  text: language.text("Your precise location is sent to our service in Hong Kong. For Taxi it is passed to DiDi; for Nearby it is reduced to about 100 m before it goes to Amap.",
                                      "精确位置会发送到我们在香港的服务。打车时转给滴滴；查找附近时，先降到约 100 米的精度再发给高德。")),
            Point(id: "keep", symbol: "tray", title: language.text("What is kept", "留存"),
                  text: language.text("We don't keep your location with your account. Amap and DiDi handle it under their own privacy policies.",
                                      "我们不会把你的位置和账号一起保存。高德和滴滴按各自的隐私政策处理。")),
            Point(id: "change", symbol: "switch.2", title: language.text("Change your mind", "撤回"),
                  text: language.text("Turn this off anytime in Me → Location, or in iOS Settings.",
                                      "可随时在「我的 → 位置」或系统设置中关闭。")),
            Point(id: "without", symbol: "keyboard", title: language.text("Without it", "不同意"),
                  text: language.text("You can type a place instead; everything else still works.",
                                      "不同意也可以手动输入地点，其他功能不受影响。")),
        ]
    }

    static func allow(_ language: LioLanguage) -> String { language.text("Allow location", "允许使用位置") }
    static func decline(_ language: LioLanguage) -> String { language.text("Not now, I'll type a place", "暂不，我手动输入") }
    static func useMyLocation(_ language: LioLanguage) -> String { language.text("Use my location", "使用我的位置") }
}

extension LioTaxiService {
    /// The pickup location behind the in-app choice (#1748); everything else is unchanged.
    @MainActor func requiringLocationConsent(_ consent: LioLocationConsent?) -> Self {
        guard let consent else { return self }
        return LioTaxiService(search: search, currentPickup: consent.gate(currentPickup), estimate: estimate,
                              rideLink: rideLink, openRideLink: openRideLink, openAppStore: openAppStore)
    }
}

extension LioTaxiEntry {
    @MainActor func requiringLocationConsent(_ consent: LioLocationConsent?) -> Self {
        LioTaxiEntry(service: service.requiringLocationConsent(consent), recentStore: recentStore, tripPlaces: tripPlaces)
    }
}

extension LioNearbyService {
    /// The current location behind the in-app choice (#1748); a missing choice reads as `.consentNeeded`.
    @MainActor func requiringLocationConsent(_ consent: LioLocationConsent?) -> Self {
        guard let consent else { return self }
        let read = consent.gate(currentLocation)
        return LioNearbyService(currentLocation: {
            do { return try await read() } catch is LioLocationConsentFailure { throw LioNearbyFailure.consentNeeded }
        }, search: search, reverse: reverse)
    }
}

/// The choice itself. Allowing records it for this account and then lets iOS ask for its own permission.
struct LioLocationConsentSheet: View {
    let language: LioLanguage
    let allow: () -> Void
    let decline: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.md) {
                    Text(LioLocationConsentCopy.title(language))
                        .font(LioTheme.display(.title).bold())
                        .foregroundStyle(LioTheme.ink)
                        .accessibilityAddTraits(.isHeader)
                    ForEach(LioLocationConsentCopy.points(language)) { point in
                        HStack(alignment: .firstTextBaseline, spacing: LioTheme.Spacing.sm) {
                            Image(systemName: point.symbol)
                                .foregroundStyle(LioTheme.vermilion)
                                .frame(width: 24)
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                                Text(point.title).font(.headline).foregroundStyle(LioTheme.ink)
                                Text(point.text).font(.body).foregroundStyle(LioTheme.inkSecondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("lio.location-consent.\(point.id)")
                    }
                }
                .padding(LioTheme.Spacing.md)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                VStack(spacing: LioTheme.Spacing.xs) {
                    Button(action: allow) {
                        Text(LioLocationConsentCopy.allow(language)).frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(.borderedProminent)
                    .foregroundStyle(LioTheme.onVermilion)
                    .accessibilityIdentifier("lio.location-consent.allow")
                    Button(action: decline) {
                        Text(LioLocationConsentCopy.decline(language)).frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.location-consent.decline")
                }
                .padding(LioTheme.Spacing.md)
                .background(LioTheme.paper)
            }
            .background(LioTheme.paper)
        }
        .tint(LioTheme.vermilion)
    }
}

/// "Use my location": opens the choice where the traveller is, and calls `allowed` once they allow it. Hidden when
/// the build does not ask for the in-app choice.
struct LioLocationConsentButton: View {
    let language: LioLanguage
    let allowed: () -> Void
    @Environment(\.lioLocationConsent) private var consent
    @State private var asking = false

    var body: some View {
        if let consent {
            Button { asking = true } label: {
                Label(LioLocationConsentCopy.useMyLocation(language), systemImage: "location")
                    .frame(minHeight: 44)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("lio.location.use")
            .sheet(isPresented: $asking) {
                LioLocationConsentSheet(language: language, allow: {
                    asking = false
                    if consent.allow() { allowed() }
                }, decline: { asking = false })
            }
        }
    }
}

/// Me → Location (#1748): whether location is on in the app, and the way to turn it off or on again.
struct LioLocationSettingsView: View {
    let language: LioLanguage
    let consent: LioLocationConsent

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: LioTheme.Spacing.xxs) {
                    Text(consent.allowed ? language.text("Location is on", "位置已开启")
                                         : language.text("Location is off", "位置已关闭"))
                        .font(.headline)
                    Text(consent.allowed
                         ? language.text("Taxi and Nearby can use your location while the app is open.",
                                         "打车和附近可以在 App 打开期间使用你的位置。")
                         : language.text("Taxi and Nearby ask before using your location. You can type a place instead.",
                                         "打车和附近会先询问再使用位置，也可以手动输入地点。"))
                        .font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                }
                .padding(.vertical, 4)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("lio.location-settings.status")
                if consent.allowed {
                    Button(role: .destructive) { consent.withdraw() } label: {
                        Text(language.text("Turn off location", "关闭位置")).frame(minHeight: 44)
                    }
                    .accessibilityIdentifier("lio.location-settings.off")
                } else {
                    LioLocationConsentButton(language: language) {}
                        .environment(\.lioLocationConsent, consent)
                }
            }
            .lioRow()
            Section {
                Button {
                    if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                } label: {
                    Text(language.text("Open iOS Settings", "打开系统设置")).frame(minHeight: 44)
                }
                .accessibilityIdentifier("lio.location-settings.system")
            } footer: {
                Text(language.text("iOS keeps its own location permission for Go2China; you can turn it off there too.",
                                   "系统对 Go2China 另有位置权限，也可以在那里关闭。"))
            }
            .lioRow()
        }
        .lioPage()
        .navigationTitle(language.text("Location", "位置"))
    }
}
#endif
