import Foundation
import Testing
@testable import CJStrictJSON

private enum WideJSONFailure: Error { case invalid }
private enum ExistingNumbers: StrictJSONPolicy { static var failure: WideJSONFailure { .invalid } }
private enum WideNumbers: StrictJSONPolicy {
    static var failure: WideJSONFailure { .invalid }
    static var preservesUnboundedNumberTokens: Bool { true }
}

struct UnboundedNumberTests {
    @Test func newPolicyPreservesLargeTokensAndExactOriginalRangesWithoutChangingTheDefault() throws {
        let huge = String(repeating: "9", count: 400)
        let phrase = #"escaped \"123"#
        let encoded = try JSONSerialization.data(withJSONObject: [phrase])
        let quoted = String(decoding: encoded, as: UTF8.self).dropFirst().dropLast()
        let text = "{\"n\":" + huge + ",\"s\":" + quoted + ",\"nested\":{\"n\":1e999},\"a\":[true,null,1.10]}"
        let data = Array(text.utf8)
        var old = StrictJSONReader<ExistingNumbers>(bytes: data)
        #expect(throws: Error.self) { try old.document() }
        var reader = StrictJSONReader<WideNumbers>(bytes: data)
        guard case .object(let fields) = try reader.document() else { Issue.record("object expected"); return }
        guard case .number(let token)? = fields["n"] else { Issue.record("number expected"); return }
        #expect(token == huge)
        #expect(String(decoding: data[try #require(reader.rootMemberRanges["n"])], as: UTF8.self) == huge)
        #expect(String(decoding: data[try #require(reader.rootMemberRanges["nested"])], as: UTF8.self) == #"{"n":1e999}"#)
        guard case .string(let string)? = fields["s"] else { Issue.record("string expected"); return }
        #expect(string == phrase)
    }

    @Test(arguments: ["01", "+1", "1.", ".1", "1e", "1e+", "--1", "1true", "1:2", "NaN", "Infinity", "-Infinity"])
    func newPolicyRetainsJSONNumberGrammarRejections(_ token: String) throws {
        var reader = StrictJSONReader<WideNumbers>(bytes: Array(("{\"n\":" + token + "}").utf8))
        #expect(throws: Error.self) { try reader.document() }
    }

    @Test(arguments: [#"{"a":1,"a":2}"#, #"{"n":1 "x":2}"#, #"{"n":1,}"#, #"[1,]"#,
                      #"[,1]"#, #"[1,,2]"#, #"{"n":1,,"x":2}"#, #"{"n":}"#, #"{"n"1}"#, "[", "{", "",
                      #"{"n":1 "# , #"{"n":1e999,"s":"\q"}"#, #"{"n":1e999,"s":"\uD800"}"#,
                      #"{"n":1e999,"s":"unterminated}"#, #"{"n":1e999} {}"#, #"1e999"#])
    func newPolicyStillRequiresCompleteUnambiguousJSON(_ text: String) throws {
        var reader = StrictJSONReader<WideNumbers>(bytes: Array(text.utf8))
        #expect(throws: Error.self) { try reader.document() }
    }

    @Test func newPolicyStillRejectsNulAndInvalidUTF8() throws {
        for bytes in [[UInt8](#"{"n":1}"#.utf8) + [0], [0x7b,0x22,0xc3,0x28,0x22,0x3a,0x31,0x7d]] {
            var reader = StrictJSONReader<WideNumbers>(bytes: bytes)
            #expect(throws: Error.self) { try reader.document() }
        }
    }
}
