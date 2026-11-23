import Foundation
import Testing
@testable import CJLioUser

struct LocalSupportDirectoryTests {
    @Test func shipsTheVerifiedMainlandNumbersWithoutAnyDialling() throws {
        let catalog = try LocalSupportDirectory.bundled()
        #expect(LocalSupportDirectory.emergencyContacts.map(\.phone.number) == ["110", "120", "119", "122"])
        #expect(LocalSupportDirectory.helpContacts.map(\.phone.number) == ["12345", "12367"])
        #expect(LocalSupportDirectory.consumerContacts.map(\.phone.number) == ["12315", "12345"])
        let all = LocalSupportDirectory.emergencyContacts + LocalSupportDirectory.helpContacts + LocalSupportDirectory.consumerContacts
        #expect(!all.map(\.phone.number).contains("12308"))
        #expect(!all.map(\.phone.number).contains("12301"))
        #expect(catalog.verifiedAt == "2026-11-23")
    }

    @Test func bundlesTheFullForeignMinistryIndexAndKeepsUnverifiedFieldsAbsent() throws {
        let catalog = try LocalSupportDirectory.bundled()
        #expect(catalog.embassies.count == 178)
        let japan = try #require(catalog.embassies.first { $0.countryCode == "JP" })
        #expect(japan.phone?.number == "+861085319800")
        #expect(japan.address?.zh == "亮马桥东街1号")
        #expect(japan.latitude == nil)
        #expect(japan.longitude == nil)
        let sanMarino = try #require(catalog.embassies.first { $0.countryCode == "SM" })
        #expect(sanMarino.address == nil)
        #expect(sanMarino.phone == nil)
    }

    @Test func fixedHotlinesAreIndependentOfAnUnreadableEmbassyCatalog() {
        #expect(throws: (any Error).self) {
            try LocalSupportDirectory.decode(Data("unreadable catalog".utf8))
        }
        #expect(LocalSupportDirectory.emergencyContacts.map(\.phone.number) == ["110", "120", "119", "122"])
        #expect(LocalSupportDirectory.helpContacts.map(\.phone.number) == ["12345", "12367"])
        #expect(LocalSupportDirectory.consumerContacts.map(\.phone.number) == ["12315", "12345"])
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
            ("39.9", "91"),
            ("\"latitude\":39.9,", "")
        ] {
            let changed = good.replacingOccurrences(of: original, with: replacement)
            #expect(throws: (any Error).self) { try LocalSupportDirectory.decode(Data(changed.utf8)) }
        }
    }
    @Test func rejectsDuplicateDirectoryKeysAndKeepsPublicNumbersAvailable() {
        let duplicate = #"{"data_version":1,"verified_at":"2026-11-23","embassies":[],"embassies":[]}"#
        #expect(throws: LocalSupportDirectory.Failure.invalidMetadata) {
            try LocalSupportDirectory.decode(Data(duplicate.utf8))
        }
        #expect(LocalSupportDirectory.emergencyContacts.map(\.phone.number) == ["110", "120", "119", "122"])
    }

}
