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
    #if os(iOS)
    private var hasUnconfirmedLookup = false
    #endif

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool,
         bearer: @escaping @MainActor () -> String?, exchange: @escaping Exchange) {
        url = baseURL.appending(path: "v1/tools/nearby/reverse")
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.exchange = exchange
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
        guard !hasUnconfirmedLookup else { return .outcomeUnknown }
        let location = LioTaxiPickupLocation()
        let coordinate: LioTaxiPlace.Coordinate
        do {
            coordinate = try await location.pickup().coordinate
        } catch {
            return location.permissionWasDenied ? .permissionDenied : .unavailable
        }
        guard !Task.isCancelled, isAvailable else { return .unavailable }
        guard !hasUnconfirmedLookup else { return .outcomeUnknown }
        hasUnconfirmedLookup = true
        do {
            let address = try await lookup(coordinate, requestID: UUID())
            hasUnconfirmedLookup = false
            return .address(address)
        } catch LioLocalAddressRelayFailure.offline {
            hasUnconfirmedLookup = false
            return .offline
        } catch LioLocalAddressRelayFailure.notEnabled {
            hasUnconfirmedLookup = false
            return .notEnabled
        } catch LioLocalAddressRelayFailure.rateLimited {
            hasUnconfirmedLookup = false
            return .rateLimited
        } catch LioLocalAddressRelayFailure.outcomeUnknown, LioLocalAddressRelayFailure.previousAttempt, is CancellationError {
            return .outcomeUnknown
        } catch {
            hasUnconfirmedLookup = false
            return .unavailable
        }
    }

    public static func internalBeta(endpoint: MessageEndpoint,
                                    isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioLocalAddressRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CLocalAddressEnabled") as? String == "YES" else {
            return nil
        }

        return LioLocalAddressRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
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
