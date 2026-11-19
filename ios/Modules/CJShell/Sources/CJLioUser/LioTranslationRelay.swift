import Foundation

enum LioRelayTranslationFailure: Error, Equatable {
    case accessDenied
    case rejected(Int)
    case invalidAudio
}

struct LioRelayTranslationRequest: Encodable {
    enum Payload {
        case text(String)
        case wav(Data)
        case jpeg(Data)
        case png(Data)
    }

    let id: UUID
    let source: LioTranslationLanguage
    let target: LioTranslationLanguage
    let payload: Payload

    private enum CodingKeys: String, CodingKey {
        case version, kind, text, media
        case id = "request_id"
        case source = "source_lang"
        case target = "target_lang"
        case mediaType = "media_type"
    }

    func encode(to encoder: any Encoder) throws {
        var body = encoder.container(keyedBy: CodingKeys.self)
        try body.encode("TRANSLATION.1", forKey: .version)
        try body.encode(id.uuidString.lowercased(), forKey: .id)
        try body.encode(wireLanguage(source), forKey: .source)
        try body.encode(wireLanguage(target), forKey: .target)
        switch payload {
        case .text(let text):
            try body.encode("text", forKey: .kind)
            try body.encode(text, forKey: .text)
        case .wav(let data): try encodeMedia(data, kind: "speech", type: "audio/wav", to: &body)
        case .jpeg(let data): try encodeMedia(data, kind: "image", type: "image/jpeg", to: &body)
        case .png(let data): try encodeMedia(data, kind: "image", type: "image/png", to: &body)
        }
    }

    private func wireLanguage(_ language: LioTranslationLanguage) -> String {
        switch language {
        case .chinese: "zh"
        case .english: "en"
        }
    }

    private func encodeMedia(_ data: Data, kind: String, type: String,
                             to body: inout KeyedEncodingContainer<CodingKeys>) throws {
        try body.encode(kind, forKey: .kind)
        try body.encode(type, forKey: .mediaType)
        try body.encode(data.base64EncodedString(), forKey: .media)
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
        let error: String
    }

    let items: [Line]

    static func decode(status: Int, body: Data) throws -> Self {
        let decoder = JSONDecoder()
        switch status {
        case 200:
            guard let decoded = try? decoder.decode(Self.self, from: body), !decoded.items.isEmpty,
                  decoded.items.allSatisfy({
                      !$0.sourceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                      && !$0.translatedText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                  }) else {
                throw LioTranslationFailure.service
            }
            return decoded
        case 401, 403: throw LioRelayTranslationFailure.accessDenied
        case 429:
            if (try? decoder.decode(ServiceError.self, from: body))?.error == "quota_exceeded" {
                throw LioTranslationFailure.quota
            }
            throw LioTranslationFailure.service
        case 500...599: throw LioTranslationFailure.service
        default: throw LioRelayTranslationFailure.rejected(status)
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
struct LioRelayTranslationClient {
    typealias Transport = @MainActor (String, Data) async throws -> (Int, Data)
    let send: Transport

    func translate(_ request: LioRelayTranslationRequest) async throws -> LioRelayTranslationResponse {
        let body = try JSONEncoder().encode(request)
        do {
            let (status, data) = try await send("/v1/tools/translate", body)
            try Task.checkCancellation()
            return try LioRelayTranslationResponse.decode(status: status, body: data)
        } catch let error as URLError {
            switch error.code {
            case .cancelled: throw CancellationError()
            case .notConnectedToInternet, .networkConnectionLost, .cannotConnectToHost, .timedOut:
                throw LioTranslationFailure.network
            default: throw error
            }
        }
    }
}
