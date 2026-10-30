import Foundation
import Testing
import CJAPI
@testable import CJMemoryClient

struct TypedMemoryCommandTests {
    let id = "0123456789abcdef0123456789abcdef"
    private func command(travel: Bool = true) throws -> TypedMemoryCommand {
        try TypedMemoryCommand(operationID:"op-original",itemID:"item-original",subject:"traveller",slot:"preference",text:"保持原文e\u{301}",occurredAt:"约去年",
            kind:.preference,travelContext:travel ? MemoryTravelSelection(id:id,expectedVersion:7) : nil)
    }
    @Test func currentIsTravelAndLongTermContainsExplicitNull() throws {
        for travel in [true,false] {
            let original = try command(travel:travel),restored = try TypedMemoryCommand(originalUTF8:original.originalUTF8)
            #expect(restored.originalUTF8 == original.originalUTF8)
            #expect(Data(restored.text.utf8) == Data("保持原文e\u{301}".utf8))
            let object = try JSONSerialization.jsonObject(with:original.originalUTF8) as! [String:Any]
            #expect(object["version"] as? String == "MEMORY-manual.2")
            #expect(object["context_id"] == nil)
            if travel { #expect(restored.travelContext?.expectedVersion == 7) }
            else { #expect(object["context"] is NSNull) }
        }
    }
    @Test func preservedOriginalWhitespaceNeverChangesItsDigest() throws {
        let raw = try command().originalUTF8
        let spaced = Data(" \n".utf8) + raw + Data("\n".utf8)
        let restored = try TypedMemoryCommand(originalUTF8:spaced),record = TypedMemoryPending(restored)
        #expect(restored.originalUTF8 == spaced && record.expectedSHA256 == digest(spaced))
        #expect(digest(raw) != record.expectedSHA256);try record.validate()
    }
    @Test func versionAliasLegacyScopeMissingAndExtraFieldsFailClosed() throws {
        let raw = try command().originalUTF8
        let original = try JSONSerialization.jsonObject(with:raw) as! [String:Any]
        var cases: [[String:Any]] = []
        var value = original;value["version"] = "MEMORY-manual.1";cases.append(value)
        value = original;value["context"] = NSNull();cases.append(value)
        value = original;value["extent"] = "long_term";cases.append(value)
        value = original;value.removeValue(forKey:"context");cases.append(value)
        value = original;value["context_id"] = id;cases.append(value)
        value = original;value["context"] = ["kind":"legacy","id":id,"expected_version":7];cases.append(value)
        for object in cases {
            let bytes = try JSONSerialization.data(withJSONObject:object)
            #expect(throws:(any Error).self) { try TypedMemoryCommand(originalUTF8:bytes) }
        }
        let duplicate = Data(String(decoding:raw,as:UTF8.self).replacingOccurrences(of:"\"expected_version\":7",with:"\"expected_version\":7,\"expected_version\":7").utf8)
        #expect(throws:(any Error).self) { try TypedMemoryCommand(originalUTF8:duplicate) }
    }
    @Test(arguments:["true","false","7.0","7e0","0","-1","9223372036854775808"])
    func travelVersionIsPositiveInt64Token(value: String) throws {
        let raw = try command().originalUTF8
        let bytes = Data(String(decoding:raw,as:UTF8.self).replacingOccurrences(of:"\"expected_version\":7",with:"\"expected_version\":" + value).utf8)
        #expect(throws:(any Error).self) { try TypedMemoryCommand(originalUTF8:bytes) }
    }
    @Test func journalCannotBeReboundToDifferentIdentifierOrBytes() throws {
        let original = TypedMemoryPending(try command())
        var object = try JSONSerialization.jsonObject(with:JSONEncoder().encode(original)) as! [String:Any]
        for field in ["operationID","itemID","expectedSHA256"] {
            var changed = object;changed[field] = "different"
            let bytes = try JSONSerialization.data(withJSONObject:changed)
            let invalid = try JSONDecoder().decode(TypedMemoryPending.self,from:bytes)
            #expect(throws:(any Error).self) { try invalid.validate() }
        }
        object["inference"] = true
        let invalid = try JSONDecoder().decode(TypedMemoryPending.self,from:JSONSerialization.data(withJSONObject:object))
        #expect(throws:(any Error).self) { try invalid.validate() }
    }
}
