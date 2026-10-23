import Foundation
import CJAuth

public enum EmailCallbackPurpose: Sendable { case verifyEmail, resetPassword }
public enum EmailCallbackKind: Sendable { case https, customScheme }
public enum EmailCallbackConfigurationFailure: Error, Equatable, Sendable { case invalidDestination }

/// Explicit trusted-host configuration syntax only; not platform/provider approval.
/// No incoming callback/code/nonce is accepted by this descriptor.
public struct HostEmailCallback: Equatable, Sendable {
    public let destination: URL
    public let kind: EmailCallbackKind
    public let purpose: EmailCallbackPurpose
    public var exactDestination: String { destination.absoluteString }

    public init(exactDestination: URL, kind: EmailCallbackKind, purpose: EmailCallbackPurpose) throws {
        guard let parts = URLComponents(url: exactDestination, resolvingAgainstBaseURL: false),
              let scheme = parts.scheme, !scheme.isEmpty, scheme == scheme.lowercased(),
              scheme.utf8.enumerated().allSatisfy({ index, c in
                  (97...122).contains(c) || (index > 0 && ((48...57).contains(c) || [43,45,46].contains(c)))
              }), let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              !exactDestination.absoluteString.contains("*"),
              !exactDestination.absoluteString.contains(where: \.isWhitespace) else {
            throw EmailCallbackConfigurationFailure.invalidDestination
        }
        switch kind {
        case .https:
            guard scheme == "https" else { throw EmailCallbackConfigurationFailure.invalidDestination }
        case .customScheme:
            guard !["http","https","file","data","javascript","about","mailto","tel"].contains(scheme),
                  parts.port == nil, !exactDestination.absoluteString.contains("%"),
                  !parts.path.split(separator: "/", omittingEmptySubsequences: false).contains(where: { $0 == "." || $0 == ".." }) else { throw EmailCallbackConfigurationFailure.invalidDestination }
        }
        self.destination = exactDestination; self.kind = kind; self.purpose = purpose
    }
    public static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.exactDestination == rhs.exactDestination && lhs.kind == rhs.kind && lhs.purpose == rhs.purpose
    }
}

/// Local request correlation, not an OAuth state/PKCE proof or incoming URL handler.
public struct AuthEmailCallbackContext: Equatable, Sendable {
    public let callback: HostEmailCallback
    public let attempt: AuthAttempt
    let owner: UUID
    init(callback: HostEmailCallback, attempt: AuthAttempt, owner: UUID) {
        self.callback = callback; self.attempt = attempt; self.owner = owner
    }
}
