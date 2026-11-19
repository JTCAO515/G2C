import CJStrictJSON
import CryptoKit
import Foundation

enum LioRelayTranslationFailure: Error, Equatable {
    case signInRequired
    case accessDenied
    case alreadyAccepted
    case rejected(Int)
    case invalidInput
    case invalidAudio
    case originalUnavailable
}

struct LioRelayTranslationRequest: Encodable {
    enum Kind: String, Codable { case text, speech, image }

    enum Payload {
        case text(String)
        case wav(Data)
        case jpeg(Data)
        case png(Data)
    }

    static let version = "TRANSLATION.1"
    private static let maximumMedia = 3 * 1024 * 1024 - 4096
    let id: UUID
    let source: LioTranslationLanguage
    let target: LioTranslationLanguage
    let payload: Payload

    func wireBody() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let body = try encoder.encode(self)
        guard body.count <= 4 * 1024 * 1024 else { throw LioRelayTranslationFailure.invalidInput }
        return body
    }

    var kind: Kind {
        switch payload {
        case .text: .text
        case .wav: .speech
        case .jpeg, .png: .image
        }
    }

    private enum CodingKeys: String, CodingKey {
        case version, kind, text, media
        case id = "request_id"
        case source = "source_lang"
        case target = "target_lang"
    }

    func encode(to encoder: any Encoder) throws {
        guard source != target else { throw LioRelayTranslationFailure.invalidInput }
        var body = encoder.container(keyedBy: CodingKeys.self)
        try body.encode(Self.version, forKey: .version)
        try body.encode(id.uuidString.lowercased(), forKey: .id)
        try body.encode(kind.rawValue, forKey: .kind)
        try body.encode(wireLanguage(source), forKey: .source)
        try body.encode(wireLanguage(target), forKey: .target)
        switch payload {
        case .text(let text):
            guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  text.unicodeScalars.count <= 4000, !text.utf8.contains(0) else {
                throw LioRelayTranslationFailure.invalidInput
            }
            try body.encode(text, forKey: .text)
        case .wav(let data):
            try encodeMedia(data, prefix: Array("RIFF".utf8), to: &body)
        case .jpeg(let data):
            try encodeMedia(data, prefix: [0xff, 0xd8, 0xff], to: &body)
        case .png(let data):
            try encodeMedia(data, prefix: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], to: &body)
        }
    }

    private func wireLanguage(_ language: LioTranslationLanguage) -> String {
        switch language {
        case .chinese: "zh"
        case .english: "en"
        }
    }

    private func encodeMedia(_ data: Data, prefix: [UInt8],
                             to body: inout KeyedEncodingContainer<CodingKeys>) throws {
        guard data.count > prefix.count, data.count <= Self.maximumMedia, data.starts(with: prefix) else {
            throw LioRelayTranslationFailure.invalidInput
        }
        try body.encode(data.base64EncodedString(), forKey: .media)
    }
}

@MainActor struct LioRelayOriginalRequests {
    private struct Identity: Codable, Hashable {
        let source: LioTranslationLanguage
        let target: LioTranslationLanguage
        let kind: LioRelayTranslationRequest.Kind
        let fingerprint: Data

        init(_ request: LioRelayTranslationRequest) {
            source = request.source
            target = request.target
            kind = request.kind
            switch request.payload {
            case .text(let text): fingerprint = Data(SHA256.hash(data: Data(text.utf8)))
            case .wav(let bytes), .jpeg(let bytes), .png(let bytes): fingerprint = Data(SHA256.hash(data: bytes))
            }
        }
    }

    private struct Original: Codable {
        let id: UUID
        let wireFingerprint: Data
        var accepted: Bool
    }

    private var memory: [Identity: Original] = [:]

    mutating func request(source: LioTranslationLanguage, target: LioTranslationLanguage,
                          payload: LioRelayTranslationRequest.Payload,
                          storage: LioTranslationHistory? = nil) throws -> LioRelayTranslationRequest {
        let proposed = LioRelayTranslationRequest(id: UUID(), source: source, target: target, payload: payload)
        let identity = Identity(proposed)
        var pending = try load(storage)
        if let original = pending[identity] {
            guard !original.accepted else { throw LioRelayTranslationFailure.alreadyAccepted }
            let request = LioRelayTranslationRequest(id: original.id, source: source, target: target, payload: payload)
            guard try wireFingerprint(request) == original.wireFingerprint else {
                throw LioRelayTranslationFailure.originalUnavailable
            }
            return request
        }
        pending[identity] = try Original(id: proposed.id, wireFingerprint: wireFingerprint(proposed), accepted: false)
        try save(pending, storage: storage)
        return proposed
    }

    mutating func accept(_ request: LioRelayTranslationRequest, storage: LioTranslationHistory? = nil) throws {
        let identity = Identity(request)
        var pending = try load(storage)
        guard pending[identity]?.id == request.id else { throw LioRelayTranslationFailure.originalUnavailable }
        pending[identity]?.accepted = true
        try save(pending, storage: storage)
    }

    mutating func confirm(_ request: LioRelayTranslationRequest, storage: LioTranslationHistory? = nil) throws {
        let identity = Identity(request)
        var pending = try load(storage)
        guard pending[identity]?.id == request.id else { throw LioRelayTranslationFailure.originalUnavailable }
        pending.removeValue(forKey: identity)
        try save(pending, storage: storage)
    }

    private func load(_ storage: LioTranslationHistory?) throws -> [Identity: Original] {
        guard let storage else { return memory }
        guard let bytes = try storage.loadRelayOriginals() else { return [:] }
        return try JSONDecoder().decode([Identity: Original].self, from: bytes)
    }

    private mutating func save(_ pending: [Identity: Original], storage: LioTranslationHistory?) throws {
        if let storage { try storage.saveRelayOriginals(JSONEncoder().encode(pending)) }
        else { memory = pending }
    }

    private func wireFingerprint(_ request: LioRelayTranslationRequest) throws -> Data {
        Data(SHA256.hash(data: try request.wireBody()))
    }
}

struct LioRelayTranslationResponse: Decodable {
    struct Line: Decodable {
        let sourceText: String
        let translatedText: String

        private enum CodingKeys: String, CodingKey {
            case sourceText = "source_text"
            case translatedText = "translated_text"
        }
    }

    private struct ServiceError: Decodable {
        let version: String
        let error: String
    }

    private enum JSONPolicy: StrictJSONPolicy {
        static let failure = LioTranslationFailure.service
        static let maximumDepth = 8
        static let requiresObjectRoot = true
    }

    let version: String
    let kind: LioRelayTranslationRequest.Kind
    let items: [Line]

    static func decode(status: Int, body: Data, expecting kind: LioRelayTranslationRequest.Kind) throws -> Self {
        switch status {
        case 401: throw LioRelayTranslationFailure.signInRequired
        case 403: throw LioRelayTranslationFailure.accessDenied
        case 409: throw LioRelayTranslationFailure.alreadyAccepted
        case 500...599: throw LioTranslationFailure.service
        case 200, 429: break
        default: throw LioRelayTranslationFailure.rejected(status)
        }

        guard body.count <= 256 * 1024 else { throw LioTranslationFailure.service }
        var reader = StrictJSONReader<JSONPolicy>(bytes: Array(body))
        do { try reader.check() } catch { throw LioTranslationFailure.service }
        let decoder = JSONDecoder()
        if status == 200 {
            guard let decoded = try? decoder.decode(Self.self, from: body),
                  decoded.version == LioRelayTranslationRequest.version, decoded.kind == kind,
                  decoded.validItemCount, decoded.items.allSatisfy({
                      !$0.sourceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                      && !$0.translatedText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                  }) else {
                throw LioTranslationFailure.service
            }
            return decoded
        }

        guard let error = try? decoder.decode(ServiceError.self, from: body),
              error.version == LioRelayTranslationRequest.version else {
            throw LioRelayTranslationFailure.rejected(status)
        }
        guard error.error == "quota_exceeded" else { throw LioRelayTranslationFailure.rejected(status) }
        throw LioTranslationFailure.quota
    }

    private var validItemCount: Bool {
        switch kind {
        case .text: items.count == 1
        case .speech: items.count <= 1
        case .image: items.count <= 24
        }
    }
}

enum LioTranslationWAV {
    static let sampleRate: UInt32 = 16_000
    static let maximumPCMBytes = Int(sampleRate) * MemoryLayout<Int16>.size * 60

    static func encode(pcm: Data) throws -> Data {
        let channels: UInt16 = 1
        let sampleBytes: UInt16 = 2
        let bytesPerSecond = sampleRate * UInt32(channels * sampleBytes)
        guard !pcm.isEmpty, pcm.count.isMultiple(of: Int(sampleBytes)), pcm.count <= maximumPCMBytes else {
            throw LioRelayTranslationFailure.invalidAudio
        }
        var output = Data("RIFF".utf8)
        append(UInt32(pcm.count + 36), to: &output)
        output.append(Data("WAVEfmt ".utf8))
        append(UInt32(16), to: &output)
        append(UInt16(1), to: &output)
        append(channels, to: &output)
        append(sampleRate, to: &output)
        append(bytesPerSecond, to: &output)
        append(channels * sampleBytes, to: &output)
        append(sampleBytes * 8, to: &output)
        output.append(Data("data".utf8))
        append(UInt32(pcm.count), to: &output)
        output.append(pcm)
        return output
    }

    private static func append<Value: FixedWidthInteger>(_ value: Value, to data: inout Data) {
        var littleEndian = value.littleEndian
        withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
    }
}

@MainActor
public struct LioRelayTranslationClient {
    public typealias Transport = @MainActor (String, Data) async throws -> (Int, Data)
    private let send: Transport
    let requiresOriginalStore: Bool

    public init(send: @escaping Transport) {
        self.init(requiresOriginalStore: false, send: send)
    }

    init(requiresOriginalStore: Bool, send: @escaping Transport) {
        self.requiresOriginalStore = requiresOriginalStore
        self.send = send
    }

    func translate(_ request: LioRelayTranslationRequest) async throws -> LioRelayTranslationResponse {
        try Task.checkCancellation()
        let body = try request.wireBody()
        do {
            let (status, data) = try await send("/v1/tools/translate", body)
            try Task.checkCancellation()
            return try LioRelayTranslationResponse.decode(status: status, body: data, expecting: request.kind)
        } catch let error as URLError {
            switch error.code {
            case .cancelled: throw CancellationError()
            case .notConnectedToInternet, .networkConnectionLost, .cannotFindHost, .dnsLookupFailed,
                 .cannotConnectToHost, .timedOut, .dataNotAllowed:
                throw LioTranslationFailure.network
            default: throw error
            }
        }
    }
}
