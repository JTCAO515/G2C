import Foundation
import Testing
@testable import CJStrictJSON

private enum Refused: Error { case json }
private enum Default: StrictJSONPolicy { static var failure: Refused { .json } }
private enum ObjectRoot: StrictJSONPolicy {
    static var failure: Refused { .json }
    static var requiresObjectRoot: Bool { true }
}
private enum Shallow: StrictJSONPolicy {
    static var failure: Refused { .json }
    static var maximumDepth: Int { 32 }
}
private enum Fragments: StrictJSONPolicy {
    static var failure: Refused { .json }
    static var allowsFragments: Bool { true }
}

private func reader<P: StrictJSONPolicy>(_ policy: P.Type, _ text: String) -> StrictJSONReader<P> { .init(bytes: Array(text.utf8)) }
private func accepted<P: StrictJSONPolicy>(_ policy: P.Type, _ bytes: Data) -> Bool {
    var reader = StrictJSONReader<P>(bytes: Array(bytes))
    return (try? reader.check()) != nil
}
private func accepted<P: StrictJSONPolicy>(_ policy: P.Type, _ text: String) -> Bool { accepted(policy, Data(text.utf8)) }
private func nested(_ depth: Int) -> String { String(repeating: "[", count: depth) + String(repeating: "]", count: depth) }

@Suite struct StrictJSONReaderTests {
    @Test(arguments: [#"{"a":1,"a":2}"#, #"{"x":{"a":1,"a":1}}"#, #"[{"a":1,"a":2}]"#, #"{"a":1,"a":2}"#])
    func duplicateKeysAreRefused(text: String) throws {
        var value = reader(Default.self, text)
        #expect(throws: Refused.self) { try value.check() }
        #expect(try JSONSerialization.jsonObject(with: Data(text.utf8)) is Any, "Foundation alone accepts this input")
    }

    @Test func alternateEncodingsAndNulAreRefusedByTheReader() throws {
        let text = #"{"a":1}"#
        for encoding in [String.Encoding.utf16LittleEndian, .utf16BigEndian, .utf32LittleEndian, .utf32BigEndian] {
            var value = StrictJSONReader<Default>(bytes: Array(try #require(text.data(using: encoding))))
            #expect(throws: Refused.self) { try value.check() }
        }
        var nul = StrictJSONReader<Default>(bytes: Array(text.utf8) + [0])
        #expect(throws: Refused.self) { try nul.check() }
        var invalid = StrictJSONReader<Default>(bytes: [0x22, 0xC3, 0x28, 0x22])
        #expect(throws: Refused.self) { try invalid.check() }
    }

    @Test func policyDifferencesStayExplicit() {
        #expect(accepted(Default.self, "[]") && !accepted(ObjectRoot.self, "[]") && accepted(ObjectRoot.self, " {} "))
        #expect(accepted(Default.self, nested(32)) && !accepted(Shallow.self, nested(33)) && accepted(Shallow.self, nested(32)))
        #expect(accepted(Default.self, nested(64)) && !accepted(Default.self, nested(65)))
        #expect(!accepted(Default.self, "1") && accepted(Fragments.self, "1") && accepted(Fragments.self, "\"s\""))
    }

    @Test func tokensArePreservedNotRounded() throws {
        var value = reader(Default.self, #"{"d":1.10,"i":12345678901234567890,"t":true,"n":null,"s":"1"}"#)
        guard case .object(let fields) = try value.document() else { Issue.record("object expected"); return }
        guard case .number("1.10")? = fields["d"], case .number("12345678901234567890")? = fields["i"],
              case .boolean(true)? = fields["t"], case .null? = fields["n"], case .string("1")? = fields["s"] else {
            Issue.record("token changed"); return
        }
    }

    @Test func rootMemberRangesCoverOriginalBytes() throws {
        let text = #"{"a" : {"b":1} , "c":"x"}"#
        var value = reader(Default.self, text)
        try value.check()
        let bytes = Array(text.utf8)
        #expect(String(decoding: bytes[try #require(value.rootMemberRanges["a"])], as: UTF8.self) == #"{"b":1}"#)
        #expect(String(decoding: bytes[try #require(value.rootMemberRanges["c"])], as: UTF8.self) == #""x""#)
        #expect(value.rootMemberRanges["b"] == nil)
    }

    @Test func integerTablesKeepTheirDistinctCoverage() throws {
        var value = reader(Default.self, #"{"a":1,"b":{"c":2},"d":[3,{"e":4}],"f":-5,"g":1.0,"h":"6","i":9223372036854775808}"#)
        try value.check()
        #expect(value.unsignedIntegers == [["a"]: 1, ["b", "c"]: 2, ["d", "0"]: 3, ["d", "1", "e"]: 4])
        #expect(value.memberUnsignedIntegers == [["a"]: 1, ["b", "c"]: 2, ["d", "1", "e"]: 4])
        #expect(value.topLevelUnsignedIntegers == ["a": 1])
    }

    @Test func nothingIsReportedBeforeOrAfterARefusal() {
        var value = reader(Default.self, #"{"a":1,"a":2}"#)
        #expect(value.unsignedIntegers.isEmpty)
        _ = try? value.check()
        #expect(value.unsignedIntegers.isEmpty)
    }
}
