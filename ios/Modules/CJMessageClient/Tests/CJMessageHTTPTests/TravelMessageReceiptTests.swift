import Foundation
import CryptoKit
import Testing
import CJAPI
@testable import CJMessageHTTP

struct TravelMessageReceiptTests {
    let id = "0123456789abcdef0123456789abcdef"
    private func original(travel: Bool = true) throws -> OriginalTravelMessageSend {
        let context = travel ? "{\"id\":\"\(id)\",\"expected_version\":9}" : "null"
        let raw = OriginalTravelMessageTests().raw(context:context,sequence:"4")
        return try OriginalTravelMessageSend(raw:raw,maximumBytes:10000)
    }
    private func receipt(_ original: OriginalTravelMessageSend) -> Components.Schemas.MessageReceipt {
        .init(message_id:original.messageID,conversation_id:original.head.conversation_id,generation:original.head.generation,
              run_id:"run-original",sequence:5,input_sha256:SHA256.hash(data:original.originalUTF8).map { String(format:"%02x",$0) }.joined())
    }
    private func reference(_ receipt: Components.Schemas.MessageReceipt,version: Int = 9,epoch: Int = 3) -> Components.Schemas.MessageTravelReference {
        .travel(.init(version:.MESSAGE_hyphen_travel_hyphen_reference_period_1,conversation_id:receipt.conversation_id,generation:receipt.generation,
            message_id:receipt.message_id,run_id:receipt.run_id,sequence:receipt.sequence,input_sha256:receipt.input_sha256,
            message_version:.MESSAGE_hyphen_send_period_2,context_kind:.travel,context_id:id,context_version:version,selection_epoch:epoch))
    }
    @Test func receiptAndReferenceKeepOriginalSelectionEpoch() throws {
        let original = try original();let receipt = receipt(original)
        let value = try ValidatedTravelMessageReceipt(receipt:receipt,reference:reference(receipt),original:original)
        guard case .travel(let ref) = value.reference else { Issue.record("wrong context kind");return }
        #expect(ref.selection_epoch == 3 && ref.sequence == 5 && ref.context_version == 9)
    }
    @Test func referenceCannotRebindVersionOrExtendEpoch() throws {
        let original = try original();let receipt = receipt(original)
        for ref in [reference(receipt,version:10),reference(receipt,epoch:0),reference(receipt,epoch:6)] {
            #expect(throws: (any Error).self) { try ValidatedTravelMessageReceipt(receipt:receipt,reference:ref,original:original) }
        }
    }
    @Test func copiedFieldsAndOriginalHashMustAgree() throws {
        let original = try original();let expected = receipt(original)
        for field in ["message","conversation","generation","run","sequence","hash"] {
            var changed = expected
            switch field {
            case "message":changed.message_id = "different"
            case "conversation":changed.conversation_id = "different"
            case "generation":changed.generation = "different"
            case "run":changed.run_id = "different"
            case "sequence":changed.sequence = 6
            default:changed.input_sha256 = String(repeating:"0",count:64)
            }
            #expect(throws: (any Error).self) { try ValidatedTravelMessageReceipt(receipt:expected,reference:reference(changed),original:original) }
        }
    }
    @Test func explicitNoneCannotBecomeTravel() throws {
        let original = try original(travel:false);let receipt = receipt(original)
        #expect(throws: (any Error).self) { try ValidatedTravelMessageReceipt(receipt:receipt,reference:reference(receipt),original:original) }
        let none = Components.Schemas.MessageTravelReference.none(.init(version:.MESSAGE_hyphen_travel_hyphen_reference_period_1,
            conversation_id:receipt.conversation_id,generation:receipt.generation,message_id:receipt.message_id,run_id:receipt.run_id,
            sequence:receipt.sequence,input_sha256:receipt.input_sha256,message_version:.MESSAGE_hyphen_send_period_2,context_kind:.none,selection_epoch:1))
        _ = try ValidatedTravelMessageReceipt(receipt:receipt,reference:none,original:original)
    }
}
