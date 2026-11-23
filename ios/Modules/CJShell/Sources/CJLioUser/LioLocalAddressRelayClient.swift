import CJStrictJSON
import Foundation
#if os(iOS)
import CJMessageHTTP
#endif

enum LioLocalAddressRelayFailure: Error, Equatable {
    case signInRequired
    case notEnabled
    case rateLimited
    case offline
    case invalidLocation
    case previousAttempt
    case outcomeUnknown
}

@MainActor public final class LioLocalAddressRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)

    private struct Lookup: Encodable {
        struct Center: Encodable {
            let lat: Double
            let lng: Double
            let coordinateSystem: String

            enum CodingKeys: String, CodingKey {
                case lat, lng
                case coordinateSystem = "coordinate_system"
            }
        }

        let version: String
        let requestID: String
        let center: Center

        enum CodingKeys: String, CodingKey {
            case version
            case requestID = "request_id"
            case center
        }
    }

    private enum ResponsePolicy: StrictJSONPolicy {
        static let failure = LioLocalAddressRelayFailure.outcomeUnknown
        static let requiresObjectRoot = true
    }

    private static let version = "NEARBY.1"
    private static let maximumResponseBytes = 4_096
    private let url: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let exchange: Exchange
    private let pendingDirectory: URL

    init(baseURL: URL, pendingDirectory: URL, isCurrent: @escaping @MainActor () -> Bool,
         bearer: @escaping @MainActor () -> String?, exchange: @escaping Exchange) {
        url = baseURL.appending(path: "v1/tools/nearby/reverse")
        self.pendingDirectory = pendingDirectory
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.exchange = exchange
    }

    func lookupOnce(_ coordinate: LioTaxiPlace.Coordinate) async throws -> String {
        try requireCurrentSession()
        guard try !hasUnconfirmedLookup() else { throw LioLocalAddressRelayFailure.previousAttempt }
        if try !pendingDirectoryExists() {
            try FileManager.default.createDirectory(at: pendingDirectory, withIntermediateDirectories: false,
                                                    attributes: [.posixPermissions: 0o700])
        }
        var directory = pendingDirectory
        var attributes = URLResourceValues()
        attributes.isExcludedFromBackup = true
        try directory.setResourceValues(attributes)
        let requestID = UUID()
        let original = Data(requestID.uuidString.lowercased().utf8)
        #if os(iOS)
        try original.write(to: pendingFile, options: [.atomic, .completeFileProtection])
        #else
        try original.write(to: pendingFile, options: .atomic)
        #endif

        do {
            let address = try await lookup(coordinate, requestID: requestID)
            try clearPending(original)
            return address
        } catch let failure as LioLocalAddressRelayFailure {
            switch failure {
            case .previousAttempt, .outcomeUnknown:
                throw failure
            default:
                try clearPending(original)
                throw failure
            }
        }
    }

    func hasUnconfirmedLookup() throws -> Bool {
        try requireCurrentSession()
        guard try pendingDirectoryExists() else { return false }
        do {
            let metadata = try pendingFile.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard metadata.isRegularFile == true, metadata.isSymbolicLink == false, metadata.fileSize == 36 else {
                throw LioLocalAddressRelayFailure.outcomeUnknown
            }
            return true
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile || error.code == .fileNoSuchFile {
            return false
        }
    }

    private func pendingDirectoryExists() throws -> Bool {
        do {
            let metadata = try pendingDirectory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard metadata.isDirectory == true, metadata.isSymbolicLink == false else {
                throw LioLocalAddressRelayFailure.outcomeUnknown
            }
            return true
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile || error.code == .fileNoSuchFile {
            return false
        }
    }

    private var pendingFile: URL {
        pendingDirectory.appending(path: "pending-address-request")
    }

    private func clearPending(_ original: Data) throws {
        try requireCurrentSession()
        do {
            guard try hasUnconfirmedLookup(), try Data(contentsOf: pendingFile) == original else {
                throw LioLocalAddressRelayFailure.outcomeUnknown
            }
            try FileManager.default.removeItem(at: pendingFile)
        } catch {
            throw LioLocalAddressRelayFailure.outcomeUnknown
        }
    }

    func lookup(_ coordinate: LioTaxiPlace.Coordinate, requestID: UUID) async throws -> String {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else {
            throw LioLocalAddressRelayFailure.signInRequired
        }
        guard (-90...90).contains(coordinate.latitude), (-180...180).contains(coordinate.longitude) else {
            throw LioLocalAddressRelayFailure.invalidLocation
        }
        let coordinateSystem = coordinate.referenceSystem == .wgs84 ? "WGS-84" : "GCJ-02"
        let payload = Lookup(version: Self.version, requestID: requestID.uuidString.lowercased(),
                             center: .init(lat: coordinate.latitude, lng: coordinate.longitude,
                                           coordinateSystem: coordinateSystem))
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys

        var request = URLRequest(url: url, timeoutInterval: 20)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try encoder.encode(payload)

        let body: Data
        let response: URLResponse
        do {
            (body, response) = try await exchange(request)
        } catch {
            try requireCurrentSession()
            if (error as? URLError)?.code == .notConnectedToInternet {
                throw LioLocalAddressRelayFailure.offline
            }
            throw LioLocalAddressRelayFailure.outcomeUnknown
        }

        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url,
              body.count <= Self.maximumResponseBytes else {
            throw LioLocalAddressRelayFailure.outcomeUnknown
        }
        switch http.statusCode {
        case 200:
            return try Self.readAddress(body)
        case 401:
            throw LioLocalAddressRelayFailure.signInRequired
        case 403:
            throw LioLocalAddressRelayFailure.notEnabled
        case 409:
            throw LioLocalAddressRelayFailure.previousAttempt
        case 429:
            throw LioLocalAddressRelayFailure.rateLimited
        default:
            throw LioLocalAddressRelayFailure.outcomeUnknown
        }
    }

    private func requireCurrentSession() throws {
        try Task.checkCancellation()
        guard isCurrent() else { throw CancellationError() }
    }

    private static func readAddress(_ body: Data) throws -> String {
        var reader = StrictJSONReader<ResponsePolicy>(bytes: Array(body))
        guard case .object(let fields) = try reader.document(),
              case .string(Self.version) = fields["version"],
              case .string("Gaode") = fields["source"],
              case .string(let address) = fields["address_zh"],
              !address.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              address.unicodeScalars.count <= 500,
              address.unicodeScalars.allSatisfy({ $0.value >= 32 }) else {
            throw LioLocalAddressRelayFailure.outcomeUnknown
        }
        return address
    }
}

#if os(iOS)
extension LioLocalAddressRelayClient {
    var isAvailable: Bool { isCurrent() }

    func resolveCurrentAddress() async -> LioLocalAddressResult {
        guard isAvailable else { return .unavailable }
        do {
            guard try !hasUnconfirmedLookup() else { return .outcomeUnknown }
        } catch {
            return .outcomeUnknown
        }
        let location = LioTaxiPickupLocation(isCurrent: isCurrent)
        let coordinate: LioTaxiPlace.Coordinate
        do {
            coordinate = try await location.pickup().coordinate
        } catch {
            return location.permissionWasDenied ? .permissionDenied : .unavailable
        }
        guard !Task.isCancelled, isAvailable else { return .unavailable }
        do {
            return .address(try await lookupOnce(coordinate))
        } catch LioLocalAddressRelayFailure.offline {
            return .offline
        } catch LioLocalAddressRelayFailure.notEnabled {
            return .notEnabled
        } catch LioLocalAddressRelayFailure.rateLimited {
            return .rateLimited
        } catch LioLocalAddressRelayFailure.outcomeUnknown, LioLocalAddressRelayFailure.previousAttempt, is CancellationError {
            return .outcomeUnknown
        } catch {
            return .unavailable
        }
    }

    public static func internalBeta(endpoint: MessageEndpoint, pendingDirectory: URL,
                                    isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioLocalAddressRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CLocalAddressEnabled") as? String == "YES" else {
            return nil
        }

        return LioLocalAddressRelayClient(baseURL: endpoint.url, pendingDirectory: pendingDirectory,
                                          isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = 20
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }

            let (stream, response) = try await session.bytes(for: request)
            let limit = min(endpoint.maximumResponseBytes, Self.maximumResponseBytes)
            guard response.expectedContentLength <= limit else {
                throw LioLocalAddressRelayFailure.outcomeUnknown
            }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioLocalAddressRelayFailure.outcomeUnknown }
                body.append(byte)
            }
            return (body, response)
        }
    }
}
#endif
