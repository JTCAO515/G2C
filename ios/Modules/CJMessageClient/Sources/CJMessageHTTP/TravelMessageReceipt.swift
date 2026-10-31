import Foundation
import CryptoKit
import CJAPI

/// Original send.2 association only. Wire reference data is not a live effect permit.
struct ValidatedTravelMessageReceipt {
    let receipt: Components.Schemas.MessageReceipt
    let reference: Components.Schemas.MessageTravelReference
    init(receipt: Components.Schemas.MessageReceipt,reference: Components.Schemas.MessageTravelReference,
         original: OriginalTravelMessageSend) throws {
        let next = original.head.last_sequence.addingReportingOverflow(1)
        let hash = SHA256.hash(data: original.originalUTF8).map { String(format:"%02x",$0) }.joined()
        guard !next.overflow,receipt.sequence == next.partialValue,
              Self.same(receipt.message_id,original.messageID),Self.same(receipt.conversation_id,original.head.conversation_id),
              Self.same(receipt.generation,original.head.generation),Self.same(receipt.input_sha256,hash),
              !receipt.run_id.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else { throw MessageHTTPFailure.invalidResponse }
        let fields: (String,String,String,String,Int,String,Int)
        switch reference {
        case .legacy: throw MessageHTTPFailure.invalidResponse
        case .none(let value):
            guard original.travelContext == nil else { throw MessageHTTPFailure.invalidResponse }
            fields = (value.message_id,value.conversation_id,value.generation,value.run_id,value.sequence,value.input_sha256,value.selection_epoch)
        case .travel(let value):
            guard let choice = original.travelContext,Self.same(value.context_id,choice.id),value.context_version == choice.expectedVersion else { throw MessageHTTPFailure.invalidResponse }
            fields = (value.message_id,value.conversation_id,value.generation,value.run_id,value.sequence,value.input_sha256,value.selection_epoch)
        }
        guard Self.same(fields.0,receipt.message_id),Self.same(fields.1,receipt.conversation_id),
              Self.same(fields.2,receipt.generation),Self.same(fields.3,receipt.run_id),fields.4 == receipt.sequence,
              Self.same(fields.5,receipt.input_sha256),(1...receipt.sequence).contains(fields.6) else { throw MessageHTTPFailure.invalidResponse }
        self.receipt = receipt;self.reference = reference
    }
    private static func same(_ a: String,_ b: String) -> Bool { Data(a.utf8) == Data(b.utf8) }
}
