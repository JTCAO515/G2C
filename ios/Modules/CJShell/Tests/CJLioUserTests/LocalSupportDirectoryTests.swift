import Foundation
import Testing
@testable import CJLioUser

struct LocalSupportDirectoryTests {
    @Test func shipsTheVerifiedMainlandNumbersWithoutAnyDialling() throws {
        let catalog = try LocalSupportDirectory.bundled()
        #expect(catalog.emergency.map(\.phone.number) == ["110", "120", "119", "122"])
        #expect(catalog.hotlines.map(\.phone.number) == ["12345", "12367"])
        #expect(catalog.consumer.map(\.phone.number) == ["12315", "12345"])
        let all = catalog.emergency + catalog.hotlines + catalog.consumer
        #expect(!all.map(\.phone.number).contains("12308"))
        #expect(!all.map(\.phone.number).contains("12301"))
        #expect(catalog.verifiedAt == "2026-11-20")
    }

    @Test func onlyAcceptsNormalizedASCIIDialStrings() throws {
        #expect(try LocalSupportPhone("110").url.absoluteString == "tel:110")
        #expect(try LocalSupportPhone("+861012345678").url.absoluteString == "tel:+861012345678")
        for bad in ["", "+", "tel:110", "110,123", "110%23", "１１０", "110\n", "+012345678", "1234567890123456"] {
            #expect(throws: LocalSupportDirectory.Failure.invalidPhone) { try LocalSupportPhone(bad) }
        }
    }

    @Test func validatesTheBundledRecordFormatBeforeExposingContacts() throws {
        let good = #"""
        {"data_version":1,"verified_at":"2026-11-20","embassies":[
          {"country_code":"ZZ","country":{"zh":"样本国","en":"Example"},"name":{"zh":"样本国驻华使馆","en":"Embassy of Example"},
           "address":{"zh":"北京测试街","en":"Test Street, Beijing"},"phone":"+861012345678",
           "website":"https://example.invalid","latitude":39.9,"longitude":116.4}
        ]}
        """#
        let catalog = try LocalSupportDirectory.decode(Data(good.utf8))
        #expect(catalog.embassies.first?.countryCode == "ZZ")
        #expect(catalog.embassies.first?.consularPhone == nil)
        for (original, replacement) in [
            ("2026-11-20", "2026-02-30"),
            ("Test Street, Beijing", ""),
            ("+861012345678", "110#"),
            ("https://example.invalid", "tel:110"),
            ("39.9", "91")
        ] {
            let changed = good.replacingOccurrences(of: original, with: replacement)
            #expect(throws: (any Error).self) { try LocalSupportDirectory.decode(Data(changed.utf8)) }
        }
    }
}
