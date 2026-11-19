import CJStrictJSON
import CryptoKit
import Foundation

enum LioRelayTranslationFailure: Error, Equatable {
    case accessDenied
    case alreadyAccepted
    case rejected(Int)
    case invalidInput
    case invalidAudio
}

struct LioRelayTranslationRequest: Encodable {
    enum Kind: String, Decodable { case text, speech, image }

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

struct LioRelayOriginalRequests {
    private struct Identity: Hashable {
        let source: LioTranslationLanguage
        let target: LioTranslationLanguage
        let kind: LioRelayTranslationRequest.Kind
        let fingerprint: SHA256.Digest

        init(_ request: LioRelayTranslationRequest) {
            source = request.source
            target = request.target
            kind = request.kind
            switch request.payload {
            case .text(let text): fingerprint = SHA256.hash(data: Data(text.utf8))
            case .wav(let bytes), .jpeg(let bytes), .png(let bytes): fingerprint = SHA256.hash(data: bytes)
            }
        }
    }

    private var pending: [Identity: UUID] = [:]

    mutating func request(source: LioTranslationLanguage, target: LioTranslationLanguage,
                          payload: LioRelayTranslationRequest.Payload) -> LioRelayTranslationRequest {
        let proposed = LioRelayTranslationRequest(id: UUID(), source: source, target: target, payload: payload)
        let identity = Identity(proposed)
        if let original = pending[identity] {
            return LioRelayTranslationRequest(id: original, source: source, target: target, payload: payload)
        }
        pending[identity] = proposed.id
        return proposed
    }

    mutating func confirm(_ original: LioRelayTranslationRequest) {
        let identity = Identity(original)
        if pending[identity] == original.id { pending.removeValue(forKey: identity) }
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
        case 401, 403: throw LioRelayTranslationFailure.accessDenied
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
    static func encode(pcm: Data) throws -> Data {
        let sampleRate: UInt32 = 16_000
        let channels: UInt16 = 1
        let sampleBytes: UInt16 = 2
        let bytesPerSecond = sampleRate * UInt32(channels * sampleBytes)
        guard !pcm.isEmpty, pcm.count.isMultiple(of: Int(sampleBytes)),
              pcm.count <= Int(bytesPerSecond * 60) else {
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

    public init(send: @escaping Transport) { self.send = send }

    func translate(_ request: LioRelayTranslationRequest) async throws -> LioRelayTranslationResponse {
        try Task.checkCancellation()
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        let body = try encoder.encode(request)
        guard body.count <= 4 * 1024 * 1024 else { throw LioRelayTranslationFailure.invalidInput }
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
