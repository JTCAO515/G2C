import Foundation
import Testing
@testable import CJTripClient

struct ManualTripErrorResponseTests {
    private func data(_ change:(inout [String:Any])->Void={ _ in }) throws -> Data {
        var error:[String:Any]=["code":"TRIP_ACCESS_UNAVAILABLE","category":"dependency","message_en":"Request unavailable","message_zh":"请求不可用 e\u{301}","outcome":"unknown","recovery":"reconcile_original"]
        change(&error)
        return try JSONSerialization.data(withJSONObject:["request_id":"00000000-0000-4000-8000-000000000286","error":error],options:[.sortedKeys])
    }
    @Test func actualBilingualBaseEnvelopeKeepsUnknownAndOriginalLanguageBytes() throws {
        let raw=try data(),value=try manualTripErrorResponse(raw)
        #expect(value.error.code=="TRIP_ACCESS_UNAVAILABLE" && value.error.outcome == .unknown && value.error.recovery == .reconcile_original)
        #expect(Data(value.error.message_zh.utf8)==Data("请求不可用 e\u{301}".utf8))
    }
    @Test func missingMistypedUnknownAndDuplicateFieldsFailClosed() throws {
        for key in ["message_en","message_zh"] {
            #expect(throws:(any Error).self) { try manualTripErrorResponse(data { $0.removeValue(forKey:key) }) }
            #expect(throws:(any Error).self) { try manualTripErrorResponse(data { $0[key]=NSNull() }) }
        }
        #expect(throws:(any Error).self) { try manualTripErrorResponse(data { $0["owner_scope"]="caller" }) }
        #expect(throws:(any Error).self) { try manualTripErrorResponse(data { $0["outcome"]="success" }) }
        #expect(throws:(any Error).self) { try manualTripErrorResponse(data { $0["recovery"]="resend" }) }
        let raw=String(decoding:try data(),as:UTF8.self).replacingOccurrences(of:"\"outcome\":\"unknown\"",with:"\"outcome\":\"unknown\",\"outcome\":\"failed\"")
        #expect(throws:(any Error).self) { try manualTripErrorResponse(Data(raw.utf8)) }
    }
}
