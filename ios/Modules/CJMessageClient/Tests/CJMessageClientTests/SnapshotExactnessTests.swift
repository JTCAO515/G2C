import Foundation
import Testing
import CJMessageClient

@Suite struct SnapshotExactnessTests {
    private func object() -> [String:Any] {
        ["version":1,
         "actions":["action-key":["messageID":"é","originalUTF8":Data("original".utf8).base64EncodedString(),"phase":"queryRequired","receipt":Data("receipt".utf8).base64EncodedString()]],
         "drafts":["draft-key":Data("draft".utf8).base64EncodedString()],
         "draftEdits":["draft-key":"3C006798-7D4F-4784-9750-998146FB646A"],
         "draftSaves":["draft-key":["conversationID":"é","generation":"é","expectedRevision":0,"confirmedRevision":1,"originalUTF8":Data("original".utf8).base64EncodedString()]]]
    }
    private func decode(_ object:[String:Any],sorted:Bool=false) throws -> Snapshot {
        try JSONDecoder().decode(Snapshot.self,from:JSONSerialization.data(withJSONObject:object,options:sorted ? [.sortedKeys]:[]))
    }
    @Test func exactOpaqueFieldsRejectCanonicalAliases() throws {
        let base=object();let original=try decode(base)
        for field in ["conversationID","generation"] {
            var changed=base;var saves=changed["draftSaves"] as! [String:[String:Any]]
            saves["draft-key"]![field]="e\u{301}";changed["draftSaves"]=saves
            #expect(try original != decode(changed))
        }
        var changed=base;var actions=changed["actions"] as! [String:[String:Any]]
        actions["action-key"]!["messageID"]="e\u{301}";changed["actions"]=actions
        #expect(try original != decode(changed))
        #expect(try original == decode(base,sorted:true)) // Serialization order is not identity.
    }
    @Test func rawReceiptRevisionAndDictionaryKeysStayExact() throws {
        let base=object();let original=try decode(base)
        for field in ["originalUTF8","receipt"] {
            var changed=base;var actions=changed["actions"] as! [String:[String:Any]]
            actions["action-key"]![field]=Data("changed".utf8).base64EncodedString();changed["actions"]=actions
            #expect(try original != decode(changed))
        }
        var changed=base;var saves=changed["draftSaves"] as! [String:[String:Any]]
        saves["draft-key"]!["expectedRevision"]=1;changed["draftSaves"]=saves
        #expect(try original != decode(changed))
        var one=base,two=base
        one["drafts"]=["é":Data("same".utf8).base64EncodedString()]
        two["drafts"]=["e\u{301}":Data("same".utf8).base64EncodedString()]
        #expect(try decode(one) != decode(two))
    }
}
