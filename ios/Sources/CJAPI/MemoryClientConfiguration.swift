import Foundation
public import OpenAPIRuntime

public extension Configuration {
    /// MEMORY recorded_at accepts RFC3339 timestamps with or without fractional seconds.
    static var memory: Configuration { Configuration(dateTranscoder: MemoryRFC3339Transcoder()) }
}

private struct MemoryRFC3339Transcoder: DateTranscoder {
    private let fractional = ISO8601DateTranscoder.iso8601WithFractionalSeconds
    private let whole = ISO8601DateTranscoder.iso8601

    func encode(_ date: Date) throws -> String { try fractional.encode(date) }
    func decode(_ value: String) throws -> Date {
        do { return try fractional.decode(value) }
        catch { return try whole.decode(value) }
    }
}
