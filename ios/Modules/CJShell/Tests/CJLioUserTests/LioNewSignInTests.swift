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

    @Test func flagIsListedAndStaysOffInTheRelease() throws {
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
        #expect(!on.contains("G2C_NEW_SIGN_IN_SCREEN_ENABLED"), "turning it on is a separate decision")
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
