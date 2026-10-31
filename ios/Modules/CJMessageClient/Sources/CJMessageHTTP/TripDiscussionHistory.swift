import Foundation
import CryptoKit
import CJAPI

public enum MessageHistoryAssociation: Sendable {
    case legacy
    case travel(Components.Schemas.MessageTravelReference)
    case trip(MessageTripReference)
    case edit(MessageEditReference)
}
/// Immutable accepted history data. Reading it does not stage a local action,
/// update a Trip choice or grant permission to replay an old message.
public struct MessageTripHistoryItem: Sendable {
    public let receipt: Components.Schemas.MessageReceipt
    public let originalUTF8: Data
    public let text: String
    public let association: MessageHistoryAssociation
}
struct TripDiscussionHistory {
    let rows: [MessageTripHistoryItem]
    let next: String?
    init(raw: Data, maximumBytes: Int, decodedLimit: Int, limit: Int, requestID: String, edit: Bool = false) throws {
        let json=try DiscussionJSON(raw,maximumBytes:maximumBytes)
        let f=try DiscussionJSON.fields(json.object,"request_id version messages next_cursor")
        guard f["version"] as? String == (edit ? "MESSAGE-history.3" : "MESSAGE-history.2"),f["request_id"] as? String == requestID,UUID(uuidString:requestID) != nil,
              let messages=f["messages"] as? [[String:Any]],messages.count<=limit else { throw MessageHTTPFailure.invalidResponse }
        next=try DiscussionJSON.nullableText(f["next_cursor"])
        var rows:[MessageTripHistoryItem]=[],remaining=decodedLimit
        for (index,item) in messages.enumerated() {
            let fields=try DiscussionJSON.fields(item,"receipt original_utf8_base64 text reference")
            _=try DiscussionJSON.fields(fields["receipt"],"message_id conversation_id generation sequence run_id input_sha256")
            _=try json.integer(["messages",String(index),"receipt","sequence"],minimum:1)
            let receipt=try JSONDecoder().decode(Components.Schemas.MessageReceipt.self,from:JSONSerialization.data(withJSONObject:fields["receipt"]!))
            guard let encoded=fields["original_utf8_base64"] as? String,let original=Data(base64Encoded:encoded),
                  original.count<=remaining,original.base64EncodedString()==encoded,let text=fields["text"] as? String else { throw MessageHTTPFailure.invalidResponse }
            remaining-=original.count
            let source=try DiscussionJSON(original,maximumBytes:decodedLimit)
            guard let mid=source.object["message_id"] as? String,let cid=source.object["conversation_id"] as? String,
                  let content=source.object["text"] as? String,DiscussionJSON.same(mid,receipt.message_id),DiscussionJSON.same(cid,receipt.conversation_id),
                  DiscussionJSON.same(content,text),SHA256.hash(data:original).map({String(format:"%02x",$0)}).joined()==receipt.input_sha256 else { throw MessageHTTPFailure.invalidResponse }
            let association:MessageHistoryAssociation
            switch source.object["version"] as? String {
            case "MESSAGE-send.4":
                guard edit else { throw MessageHTTPFailure.invalidResponse }
                let command=try OriginalTripEdit(raw:original,maximumBytes:decodedLimit,expectedMessageID:receipt.message_id)
                let reference=try MessageEditReference.read(fields["reference"],json:json,path:["messages",String(index),"reference"])
                try reference.validate(receipt:receipt,original:command);association = .edit(reference)
            case "MESSAGE-send.3":
                let command=try OriginalTripDiscussion(raw:original,maximumBytes:decodedLimit,expectedMessageID:receipt.message_id)
                let reference=try MessageTripReference.read(fields["reference"],json:json,path:["messages",String(index),"reference"])
                try reference.validate(receipt:receipt,original:command);association = .trip(reference)
            case "MESSAGE-send.2":
                let command=try OriginalTravelMessageSend(raw:original,maximumBytes:decodedLimit,expectedMessageID:receipt.message_id)
                let ref=try DiscussionJSON.fields(fields["reference"],"version conversation_id generation message_id run_id sequence input_sha256 message_version context_kind context_id context_version selection_epoch")
                let path=["messages",String(index),"reference"]
                _=try json.integer(path+["sequence"],minimum:1);_=try json.integer(path+["selection_epoch"],minimum:1)
                if !(ref["context_version"] is NSNull) { _=try json.integer(path+["context_version"],minimum:1) }
                let reference=try JSONDecoder().decode(Components.Schemas.MessageTravelReference.self,from:JSONSerialization.data(withJSONObject:ref))
                _=try ValidatedTravelMessageReceipt(receipt:receipt,reference:reference,original:command);association = .travel(reference)
            case "MESSAGE-send.1","MESSAGE-draft.1":
                guard fields["reference"] is NSNull else { throw MessageHTTPFailure.invalidResponse }
                association = .legacy
            default:throw MessageHTTPFailure.invalidResponse
            }
            rows.append(.init(receipt:receipt,originalUTF8:original,text:text,association:association))
        }
        self.rows=rows
    }
}
