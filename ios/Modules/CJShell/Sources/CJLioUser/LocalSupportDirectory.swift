import Foundation

struct LocalSupportPhone: Decodable, Equatable, Sendable {
    let number: String

    init(_ number: String) throws {
        let international = number.hasPrefix("+")
        let digits = international ? number.utf8.dropFirst() : number.utf8[...]
        guard (international ? 8...15 : 3...15).contains(digits.count),
              digits.allSatisfy({ (48...57).contains($0) }),
              !international || digits.first != 48 else {
            throw LocalSupportDirectory.Failure.invalidPhone
        }
        self.number = number
    }

    fileprivate init(mainlandShortNumber: Int) {
        number = String(mainlandShortNumber)
    }

    init(from decoder: any Decoder) throws {
        try self.init(decoder.singleValueContainer().decode(String.self))
    }

    var url: URL { URL(string: "tel:" + number)! }
}

struct LocalSupportDirectory: Sendable {
    enum Failure: Error, Equatable {
        case missingResource, invalidMetadata, invalidPhone, invalidEmbassy, duplicateCountry
    }

    struct Text: Decodable, Sendable {
        let zh: String
        let en: String

        func localized(_ language: LioLanguage) -> String { language.text(en, zh) }

        fileprivate var isComplete: Bool {
            !zh.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && !en.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }

    struct Contact: Identifiable, Sendable {
        let id: String
        let title: Text
        let phone: LocalSupportPhone
        let detail: Text?

        fileprivate init(_ id: String, _ zh: String, _ en: String, _ number: Int,
                         detail: Text? = nil) {
            self.id = id
            title = Text(zh: zh, en: en)
            phone = LocalSupportPhone(mainlandShortNumber: number)
            self.detail = detail
        }
    }

    struct Embassy: Decodable, Identifiable, Sendable {
        let countryCode: String
        let country: Text
        let name: Text
        let address: Text?
        let phone: LocalSupportPhone?
        let consularPhone: LocalSupportPhone?
        let website: URL?
        let latitude: Double?
        let longitude: Double?
        var id: String { countryCode }

        fileprivate var isValid: Bool {
            countryCode.utf8.count == 2 && countryCode.utf8.allSatisfy { (65...90).contains($0) }
                && country.isComplete && name.isComplete && address?.isComplete != false
                && website.map(Self.isWebAddress) != false && hasValidCoordinates
        }

        private static func isWebAddress(_ url: URL) -> Bool {
            (url.scheme == "https" || url.scheme == "http")
                && url.host?.isEmpty == false && url.user == nil && url.password == nil
        }

        private var hasValidCoordinates: Bool {
            switch (latitude, longitude) {
            case let (latitude?, longitude?):
                (-90...90).contains(latitude) && (-180...180).contains(longitude)
            case (nil, nil):
                true
            default:
                false
            }
        }
    }

    private struct EmbassyFile: Decodable {
        let dataVersion: Int
        let verifiedAt: String
        let embassies: [Embassy]
    }

    let dataVersion: Int
    let verifiedAt: String
    let embassies: [Embassy]

    static func bundled() throws -> Self {
        guard let file = Bundle.module.url(forResource: "LocalSupportDirectory.v1", withExtension: "json") else {
            throw Failure.missingResource
        }
        return try decode(Data(contentsOf: file))
    }

    static func decode(_ data: Data) throws -> Self {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let file = try decoder.decode(EmbassyFile.self, from: data)
        let date = ISO8601DateFormatter()
        date.formatOptions = [.withFullDate]
        guard file.dataVersion == 1, let verified = date.date(from: file.verifiedAt),
              date.string(from: verified) == file.verifiedAt else { throw Failure.invalidMetadata }
        guard file.embassies.allSatisfy(\.isValid) else { throw Failure.invalidEmbassy }
        guard Set(file.embassies.map(\.countryCode)).count == file.embassies.count else {
            throw Failure.duplicateCountry
        }
        return Self(dataVersion: file.dataVersion, verifiedAt: file.verifiedAt, embassies: file.embassies)
    }

    static let emergencyContacts = [
        Contact("police", "报警", "Police", 110),
        Contact("ambulance", "急救", "Ambulance", 120),
        Contact("fire", "火警", "Fire", 119),
        Contact("traffic", "交通事故", "Traffic accidents", 122),
    ]

    static let helpContacts = [
        Contact("city", "政务服务便民热线", "City Service Hotline", 12345,
                detail: Text(zh: "接通后可询问是否提供英语服务。", en: "Ask whether English is available when you connect.")),
        Contact("immigration", "国家移民管理局服务热线", "National Immigration Administration Hotline", 12367,
                detail: Text(zh: "咨询签证、出入境和居留。", en: "For visas, entry, exit and residence.")),
    ]

    static let consumerContacts = [
        Contact("consumer", "全国市场监管投诉举报热线", "Consumer Complaints Hotline", 12315,
                detail: Text(zh: "反映购物、餐饮和价格问题。", en: "For shopping, dining and pricing complaints.")),
        Contact("tourism", "旅游投诉", "Tourism complaints", 12345,
                detail: Text(zh: "通过当地政务服务热线反映旅游问题。", en: "Contact the local public service hotline about tourism complaints.")),
    ]
}
