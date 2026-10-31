import Foundation
import CJAPI

/// Immutable original association, never a current travel/effect permission.
/// Constructed at the accepted-source boundary and compared byte-exactly on reads.
struct RunTravelReference {
    let value: Components.Schemas.MessageTravelReference
    private let encoded: Data
    init(_ value: Components.Schemas.MessageTravelReference,receipt: Components.Schemas.MessageReceipt) throws {
        let fields: (String,String,String,String,Int,String,Int)
        switch value {
        case .legacy:throw RunDisplayFailure.invalidReference
        case .none(let item):
            fields = (item.message_id,item.conversation_id,item.generation,item.run_id,item.sequence,item.input_sha256,item.selection_epoch)
        case .travel(let item):
            guard item.context_id.utf8.count == 32,item.context_id.utf8.allSatisfy({ (48...57).contains($0) || (97...102).contains($0) }),
                  item.context_version > 0 else { throw RunDisplayFailure.invalidReference }
            fields = (item.message_id,item.conversation_id,item.generation,item.run_id,item.sequence,item.input_sha256,item.selection_epoch)
        }
        guard exact(fields.0,receipt.message_id),exact(fields.1,receipt.conversation_id),exact(fields.2,receipt.generation),
              exact(fields.3,receipt.run_id),fields.4 == receipt.sequence,exact(fields.5,receipt.input_sha256),
              receipt.sequence > 0,(1...receipt.sequence).contains(fields.6) else { throw RunDisplayFailure.invalidReference }
        self.value = value;encoded = try Self.encode(value)
    }
    func requireOriginal(_ reference: Components.Schemas.MessageTravelReference) throws {
        guard try Self.encode(reference) == encoded else { throw RunDisplayFailure.invalidReference }
    }
    private static func encode(_ reference: Components.Schemas.MessageTravelReference) throws -> Data {
        let encoder = JSONEncoder();encoder.outputFormatting = [.sortedKeys,.withoutEscapingSlashes]
        return try encoder.encode(reference)
    }
}
