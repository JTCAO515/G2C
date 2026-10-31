import Foundation
import Testing
@testable import CJManualPreviewClient

struct ScopedActionTests {
    let trace="00000000-0000-4000-8000-000000000337"
    let hash=String(repeating:"a",count:64)
    private func action(_ kind:ScopedAction.Kind = .accept) throws -> ScopedAction {
        try .init(actionID:"original-action",kind:kind,proposalID:"original-proposal",candidateHash:hash)
    }
    private func response(_ original:ScopedAction,change:(inout [String:Any])->Void={_ in}) throws -> Data {
        var receipt:[String:Any]=["action_id":original.actionID,"kind":original.kind.rawValue,"proposal_id":original.proposalID,
            "candidate_hash":original.candidateHash,"trip_id":"formal-trip","committed_version":original.kind == .accept ? 8 : NSNull()]
        change(&receipt)
        return try JSONSerialization.data(withJSONObject:["version":"TRIP-scoped-result.1","request_id":trace,"receipt":receipt],options:[.sortedKeys])
    }
    @Test func immutableCanonicalActionKeepsOriginalIDAndBytes() throws {
        let a=try action(),restored=try ScopedAction(originalUTF8:a.originalUTF8)
        #expect(restored.actionID==a.actionID && restored.kind == .accept && restored.originalUTF8==a.originalUTF8)
        let distinct=try ScopedAction.stage(kind:.accept,proposalID:a.proposalID,candidateHash:a.candidateHash)
        #expect(distinct.actionID != a.actionID)
        #expect(throws:(any Error).self) { try ScopedAction(originalUTF8:Data(" ".utf8)+a.originalUTF8) }
        let duplicate=Data("{\"version\":\"TRIP-scoped-action.1\",".utf8)+a.originalUTF8.dropFirst()
        #expect(throws:(any Error).self) { try ScopedAction(originalUTF8:duplicate) }
    }
    @Test func oldOrUnknownFieldsCannotAcquireScopedActionMeaning() throws {
        var object=try #require(JSONSerialization.jsonObject(with:action().originalUTF8) as? [String:Any])
        object["owner"]="caller"
        #expect(throws:(any Error).self) { try ScopedAction(originalUTF8:JSONSerialization.data(withJSONObject:object,options:[.sortedKeys])) }
        object.removeValue(forKey:"owner");object["version"]="TRIP-needs-action.1"
        #expect(throws:(any Error).self) { try ScopedAction(originalUTF8:JSONSerialization.data(withJSONObject:object,options:[.sortedKeys])) }
    }
    @Test func acceptAndRejectReceiptsMatchOnlyTheExactOriginalCandidate() throws {
        for kind in [ScopedAction.Kind.accept,.reject] {
            let a=try action(kind),bytes=try response(a)
            let receipt=try ScopedActionReceipt.decode(bytes,requestID:trace,original:a,tripID:"formal-trip",expectedVersion:7,maximumBytes:32768)
            #expect(receipt?.responseUTF8==bytes && receipt?.actionID==a.actionID)
            #expect(receipt?.committedVersion == (kind == .accept ? 8 : nil))
        }
    }
    @Test(arguments:["action_id","kind","proposal_id","candidate_hash","trip_id","committed_version"])
    func changedReceiptNeverSettlesAnotherOriginal(field:String) throws {
        let a=try action()
        let bytes=try response(a) { value in
            switch field {
            case "committed_version":value[field]=9
            case "candidate_hash":value[field]=String(repeating:"b",count:64)
            case "kind":value[field]="reject"
            default:value[field]="other-original"
            }
        }
        #expect(throws:(any Error).self) { try ScopedActionReceipt.decode(bytes,requestID:trace,original:a,tripID:"formal-trip",expectedVersion:7,maximumBytes:32768) }
    }
    @Test(arguments:["true","8.0","8e0","0","-1","9223372036854775808","null","\"8\""])
    func versionLexemesAreNotCoerced(token:String) throws {
        let a=try action(),raw=try response(a)
        let bytes=Data(String(decoding:raw,as:UTF8.self).replacingOccurrences(of:"\"committed_version\":8",with:"\"committed_version\":"+token).utf8)
        #expect(throws:(any Error).self) { try ScopedActionReceipt.decode(bytes,requestID:trace,original:a,tripID:"formal-trip",expectedVersion:7,maximumBytes:32768) }
    }
    @Test func nullReceiptAndWrongEnvelopeDoNotBecomeASettledAction() throws {
        let a=try action()
        let missing=try JSONSerialization.data(withJSONObject:["version":"TRIP-scoped-result.1","request_id":trace,"receipt":NSNull()])
        #expect(try ScopedActionReceipt.decode(missing,requestID:trace,original:a,tripID:"formal-trip",expectedVersion:7,maximumBytes:32768)==nil)
        let raw=try response(a)
        #expect(throws:(any Error).self) { try ScopedActionReceipt.decode(raw,requestID:UUID().uuidString,original:a,tripID:"formal-trip",expectedVersion:7,maximumBytes:32768) }
        #expect(throws:(any Error).self) { try ScopedActionReceipt.decode(raw,requestID:trace,original:a,tripID:"formal-trip",expectedVersion:Int64.max,maximumBytes:32768) }
        #expect(throws:(any Error).self) { try ScopedActionReceipt.decode(raw,requestID:trace,original:a,tripID:"formal-trip",expectedVersion:7,maximumBytes:raw.count-1) }
    }
}
