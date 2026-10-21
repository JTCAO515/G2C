import Auth
import Foundation

/// Compile-time SDK integration only. Never constructed by the UI or tests.
/// Supplied transport/session is caller-owned. No real login in this spike.
public enum AuthProbe {
    public static func signIn(client: AuthClient, email: String, password: String) async throws -> Session {
        try await client.signIn(email: email, password: password)
    }
}
