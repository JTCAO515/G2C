// Pin-only probe, not a new parser or product test. No transport or credentials.
import Foundation
import CJAPI
import OpenAPIRuntime

@main struct DateConfigurationCheck {
    static func main() throws {
        let transcoder = Configuration.memory.dateTranscoder
        let whole = try transcoder.decode("2026-10-22T00:00:00Z")
        let fractional = try transcoder.decode("2026-10-22T00:00:00.125Z")
        precondition(abs(fractional.timeIntervalSince(whole) - 0.125) < 0.00001)
        let roundTrip = try transcoder.decode(transcoder.encode(fractional))
        precondition(roundTrip == fractional)
        do {
            _ = try transcoder.decode("not-a-date")
            fatalError("invalid date accepted")
        } catch is DecodingError { }
        print("PASS official Configuration.memory whole/fractional RFC3339, round-trip, invalid date rejection; no IO")
    }
}
