import Foundation
import Testing
@testable import CJLioUser

/// #1891: the new sign-in screen sits behind its own flag, off unless the build says YES, and its three channels
/// are placeholders that send nothing.
struct LioNewSignInTests {
    private static let shell = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private static let ios = shell.deletingLastPathComponent().deletingLastPathComponent()
    private static let source = shell.appendingPathComponent("Sources/CJLioUser/LioSignInScreen.swift")

    @Test func flagIsOnOnlyForYes() {
        #expect(LioNewSignInFeature.infoKey == "G2CNewSignInScreenEnabled")
        #expect(LioNewSignInFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "1", true, 1, "$(G2C_NEW_SIGN_IN_SCREEN_ENABLED)"] {
            #expect(!LioNewSignInFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
    }

    @Test func flagIsListedAndOnInTheRelease() throws {
        let plist = try String(contentsOf: Self.ios.appendingPathComponent("App/Info.plist"), encoding: .utf8)
        #expect(plist.contains("<key>G2CNewSignInScreenEnabled</key><string>$(G2C_NEW_SIGN_IN_SCREEN_ENABLED)</string>"))
        let project = try String(contentsOf: Self.ios.appendingPathComponent("CJProbeApp.xcodeproj/project.pbxproj"),
                                 encoding: .utf8)
        #expect(!project.contains("G2C_NEW_SIGN_IN_SCREEN_ENABLED"), "the setting stays unset in the project")
        let manifestURL = Self.ios.deletingLastPathComponent().appendingPathComponent("tooling/release/app_flags.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let flags = try #require(manifest["flags"] as? [[String: String]])
        #expect(flags.contains(["setting": "G2C_NEW_SIGN_IN_SCREEN_ENABLED", "plist": "G2CNewSignInScreenEnabled"]))
        let release = try #require(manifest["release"] as? [String: Any])
        let on = try #require(release["on"] as? [String])
        // On for the internal build since the coordinator's approval (2026-11-26); the setting itself stays unset in the
        // project, so Debug and CI builds are unchanged.
        #expect(on.contains("G2C_NEW_SIGN_IN_SCREEN_ENABLED"))
    }

    @Test func channelsUseTheProvidersWordingInBothLanguages() {
        #expect(LioSignInChannel.allCases == [.apple, .google, .email])
        #expect(LioSignInChannel.apple.title(.english) == "Sign in with Apple")
        #expect(LioSignInChannel.apple.title(.chinese) == "通过 Apple 登录")
        #expect(LioSignInChannel.google.title(.english) == "Sign in with Google")
        #expect(LioSignInChannel.google.title(.chinese) == "使用 Google 账号登录")
        for channel in LioSignInChannel.allCases {
            #expect(channel.comingSoon(.english).contains("coming soon"))
            #expect(channel.comingSoon(.english).contains("invitation code"))
            #expect(channel.comingSoon(.chinese).contains("即将开放"))
            #expect(channel.comingSoon(.chinese).contains("请先使用内部测试邀请码"))
        }
    }

    /// Text on the sign-in screens keeps 4.5:1 in both appearances, on the plain page and where all three glows
    /// overlap at their brightest (the worst case behind any text), and on the field colour used by cards.
    @Test func textKeepsContrastOverTheGlows() {
        typealias C = LioSignInColors
        for dark in [false, true] {
            func value(_ pair: C.Pair) -> UInt32 { dark ? pair.dark : pair.light }
            let peak = dark ? C.glowPeakDark : C.glowPeakLight
            var stacked = Self.rgb(value(C.base))
            for glow in [C.ember, C.amber, C.iris] { stacked = Self.blend(Self.rgb(value(glow)), over: stacked, alpha: peak) }
            for (name, text) in [("ink", C.ink), ("inkSecondary", C.inkSecondary)] {
                let colour = Self.rgb(value(text))
                for (backdrop, background) in [("page", Self.rgb(value(C.base))), ("glows", stacked),
                                               ("field", Self.rgb(value(C.field)))] {
                    let ratio = Self.contrast(colour, background)
                    #expect(ratio >= 4.5, "\(name) on \(backdrop), dark \(dark): \(ratio)")
                }
            }
            // The language switch (Lio theme ink colours) sits on a field-coloured chip at 70% over the glows.
            func theme(_ name: String) -> [Double] {
                let swatch = LioTheme.swatches.first { $0.name == name }!
                return Self.rgb(dark ? swatch.dark : swatch.light)
            }
            let chip = Self.blend(Self.rgb(value(C.field)), over: stacked, alpha: 0.7)
            for name in ["ink", "inkSecondary"] {
                let ratio = Self.contrast(theme(name), chip)
                #expect(ratio >= 4.5, "language \(name) on the chip, dark \(dark): \(ratio)")
            }
            // "Continue": disabled text on the line colour; enabled text on vermilion.
            #expect(Self.contrast(Self.rgb(value(C.inkSecondary)), Self.rgb(value(C.line))) >= 4.5, "disabled, dark \(dark)")
            #expect(Self.contrast(theme("onVermilion"), theme("vermilion")) >= 4.5, "enabled, dark \(dark)")
            #expect(Self.contrast(Self.rgb(value(C.appleText)), Self.rgb(value(C.appleFill))) >= 4.5)
            #expect(Self.contrast(Self.rgb(value(C.googleText)), Self.rgb(value(C.googleFill))) >= 4.5)
        }
    }

    private static func rgb(_ hex: UInt32) -> [Double] {
        [Double((hex >> 16) & 0xFF), Double((hex >> 8) & 0xFF), Double(hex & 0xFF)]
    }

    private static func blend(_ top: [Double], over bottom: [Double], alpha: Double) -> [Double] {
        zip(top, bottom).map { alpha * $0 + (1 - alpha) * $1 }
    }

    private static func contrast(_ a: [Double], _ b: [Double]) -> Double {
        func luminance(_ c: [Double]) -> Double {
            let l = c.map { v -> Double in
                let s = v / 255
                return s <= 0.03928 ? s / 12.92 : pow((s + 0.055) / 1.055, 2.4)
            }
            return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2]
        }
        let (x, y) = (luminance(a), luminance(b))
        return (max(x, y) + 0.05) / (min(x, y) + 0.05)
    }

    /// The placeholders only show a message: the screen has no networking, no sign-in frameworks and no stored
    /// input of its own.
    @Test func placeholdersSendAndKeepNothing() throws {
        let text = try String(contentsOf: Self.source, encoding: .utf8)
        for forbidden in ["URLSession", "URLRequest", "AuthenticationServices", "ASAuthorization",
                          "ASWebAuthenticationSession", "UserDefaults", "@AppStorage", "Keychain", "openURL", "TextField("] {
            #expect(!text.contains(forbidden), "\(forbidden)")
        }
    }
}
