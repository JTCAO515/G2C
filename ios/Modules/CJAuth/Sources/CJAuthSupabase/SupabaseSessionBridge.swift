import Foundation
import CryptoKit
import Auth
import CJSession

public enum SessionRevalidationReason: Sendable { case explicitRestore, refresh, backgroundRevalidation }
/// Only an authoritative SDK/host response may be invalid. Transport errors are unknown.
public enum SDKSessionCheck: Sendable { case verified(Session), invalid, unknown }
public enum SessionBridgeResult: Equatable, Sendable {
    case unavailable, readyToSave, stored, invalidated, identityInvalid, networkUnknown
    case malformedMaterial, identityMismatch, stale, operationConflict
    case storageFailure(SessionFailure)
}

/// One bridge per ORIGINAL SessionOperation. Default has no verifier, network or activation.
/// Uses Supabase Swift 2.55.4 Session and its official encoder/decoder, not a second credential schema.
@MainActor public final class SupabaseSessionBridge {
    public static let interfaceVersion = "CJ-SDK-SESSION-BRIDGE@0.1.0-rc.1"
    private let lifecycle: SessionLifecycle
    private let original: SessionOperation
    private let expectedUserID: UUID
    private let uiIsCurrent: @MainActor () -> Bool
    private let verify: (@MainActor (Session, SessionRevalidationReason) async -> SDKSessionCheck)?
    private let bridgeID = UUID()
    private var work: Task<SessionBridgeResult, Never>?
    private var digest: Data?
    private var originalReason: SessionRevalidationReason?
    private var verifiedMaterial: SessionMaterial?
    private var invalid = false
    private var committed = false
    public private(set) var committedOperation: SessionOperation?
    public var canUseRestrictedBusiness: Bool { false }

    public init(lifecycle: SessionLifecycle, operation: SessionOperation, expectedUserID: UUID,
                uiIsCurrent: @escaping @MainActor () -> Bool,
                verify: (@MainActor (Session, SessionRevalidationReason) async -> SDKSessionCheck)? = nil) {
        self.lifecycle = lifecycle; original = operation; self.expectedUserID = expectedUserID
        self.uiIsCurrent = uiIsCurrent; self.verify = verify
    }
    private var current: Bool { uiIsCurrent() && lifecycle.isCurrent(original) }
    private static func encode(_ session: Session) throws -> SessionMaterial {
        try SessionMaterial(trustedSDKBytes: AuthClient.Configuration.jsonEncoder.encode(session))
    }
    private static func validShape(_ session: Session) -> Bool {
        !session.accessToken.isEmpty && !session.refreshToken.isEmpty && session.tokenType == "bearer"
            && session.expiresIn.isFinite && session.expiresIn >= 0 && session.expiresAt.isFinite
    }

    /// Host's initial trusted SDK completion: save using a pre-captured SAVE operation.
    public static func saveTrustedSDKSession(_ session: Session, lifecycle: SessionLifecycle,
        operation: SessionOperation, expectedUserID: UUID, uiIsCurrent: @MainActor () -> Bool) -> SessionBridgeResult {
        guard uiIsCurrent(), lifecycle.isCurrent(operation) else { return .stale }
        guard session.user.id == expectedUserID else { return .identityMismatch }
        guard validShape(session) else { return .malformedMaterial }
        do {
            let material = try encode(session)
            guard uiIsCurrent(), lifecycle.isCurrent(operation) else { return .stale }
            try lifecycle.save(material, for: operation)
            return uiIsCurrent() && lifecycle.isCurrent(operation) ? .stored : .stale
        } catch {
            guard uiIsCurrent(), lifecycle.ownsOperation(operation) else { return .stale }
            return .storageFailure(error as? SessionFailure ?? .malformedRecord)
        }
    }

    public func revalidate(_ material: SessionMaterial, reason: SessionRevalidationReason) async -> SessionBridgeResult {
        guard current, !Task.isCancelled else { return .stale }
        guard verify != nil else { return .unavailable }
        guard original.sdkBridgeClaim.claim(bridgeID) else { return .operationConflict }
        let fingerprint = material.withBytes { Data(SHA256.hash(data: $0)) }
        if let work {
            guard digest == fingerprint, originalReason == reason else { return .operationConflict }
            let result = await work.value
            return current && !Task.isCancelled ? result : .stale
        }
        digest = fingerprint; originalReason = reason
        let task = Task { await self.run(material, reason: reason) }
        work = task // publish before await, no duplicate refresh for this operation
        let result = await task.value
        return current && !Task.isCancelled ? result : .stale
    }
    private func run(_ material: SessionMaterial, reason: SessionRevalidationReason) async -> SessionBridgeResult {
        guard current, let verify else { return .stale }
        let session: Session
        do { session = try material.withBytes { try AuthClient.Configuration.jsonDecoder.decode(Session.self, from: $0) } }
        catch { return .malformedMaterial }
        guard Self.validShape(session) else { return .malformedMaterial }
        guard session.user.id == expectedUserID else { return .identityMismatch }
        let result = await verify(session, reason)
        guard current, !Task.isCancelled else { return .stale }
        switch result {
        case .unknown:
            lifecycle.noteNetworkUnknown()
            return .networkUnknown // no deletion, write, new operation or retry
        case .invalid:
            invalid = true
            return .identityInvalid // host must verify original UI binding before explicit clear
        case .verified(let updated):
            guard updated.user.id == expectedUserID else { return .identityMismatch }
            guard Self.validShape(updated) else { return .malformedMaterial }
            do { verifiedMaterial = try Self.encode(updated) }
            catch { return .malformedMaterial }
            return .readyToSave // keep original restore operation current for the host callback
        }
    }
    /// Invoke AFTER host accepts the result against the original restore/UI binding.
    /// This intentionally advances SessionOperation; host may adopt committedOperation.
    public func persistVerified() -> SessionBridgeResult {
        guard current, !committed, let material = verifiedMaterial else { return .stale }
        committed = true; verifiedMaterial = nil
        var saveOperation: SessionOperation?
        do {
            let save = try lifecycle.beginTrustedSDKSave()
            saveOperation = save
            guard uiIsCurrent(), lifecycle.isCurrent(save) else { return .stale }
            try lifecycle.save(material, for: save)
            guard uiIsCurrent(), lifecycle.isCurrent(save) else { return .stale }
            committedOperation = save
            return .stored
        } catch {
            guard uiIsCurrent() else { return .stale }
            if let saveOperation, !lifecycle.ownsOperation(saveOperation) { return .stale }
            return .storageFailure(error as? SessionFailure ?? .storageUnavailable)
        }
    }
    public func clearAuthoritativelyInvalid() -> SessionBridgeResult {
        guard current, invalid, !committed else { return .stale }
        committed = true
        do {
            try lifecycle.clear()
            let clearedGeneration = lifecycle.identityGeneration
            guard uiIsCurrent(), lifecycle.identityGeneration == clearedGeneration,
                  lifecycle.state == .cleared else { return .stale }
            return .invalidated
        } catch {
            if error as? SessionFailure == .staleOperation { return .stale }
            let failedGeneration = lifecycle.identityGeneration
            guard uiIsCurrent(), lifecycle.identityGeneration == failedGeneration else { return .stale }
            return .storageFailure(error as? SessionFailure ?? .storageUnavailable)
        }
    }
}
