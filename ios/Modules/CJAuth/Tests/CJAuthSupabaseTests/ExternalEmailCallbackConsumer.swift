import Foundation
import CJAuth
import CJAuthSupabase

// Also typechecked as a different package; metadata only, default service remains off.
func externalCallbackConfiguration(_ exactURL: URL) throws -> SupabaseAdapterConfiguration {
    let descriptor = try HostEmailCallback(exactDestination: exactURL, kind: .customScheme, purpose: .verifyEmail)
    return SupabaseAdapterConfiguration(emailVerificationCallback: descriptor)
}
@MainActor func externalCurrentEmailContext(_ adapter: SupabaseSDKAdapter, _ attempt: AuthAttempt) -> AuthEmailCallbackContext? {
    adapter.emailCallbackContext(for: attempt, purpose: .verifyEmail)
}
