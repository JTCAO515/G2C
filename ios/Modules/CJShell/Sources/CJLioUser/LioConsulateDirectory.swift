import Foundation

struct LioConsulate: Decodable, Identifiable {
    let nameZh: String
    let nameEn: String?
    let countryZh: String
    let cityZh: String
    let source: URL
    let addressZh: String?
    let addressEn: String?
    let districtZh: String?
    let districtEn: String?

    private static let commonCountryNames = [
        "英国": "大不列颠及北爱尔兰联合王国", "uk": "大不列颠及北爱尔兰联合王国",
        "united kingdom": "大不列颠及北爱尔兰联合王国",
        "美国": "美利坚合众国", "us": "美利坚合众国", "usa": "美利坚合众国",
        "united states": "美利坚合众国",
        "韩国": "大韩民国", "south korea": "大韩民国", "republic of korea": "大韩民国",
        "朝鲜": "朝鲜民主主义人民共和国", "north korea": "朝鲜民主主义人民共和国",
        "dprk": "朝鲜民主主义人民共和国",
    ]

    var id: URL { source }

    var additionalDistrictSource: URL? {
        guard source.path == "/web/lbfw_673061/lsgmd_673079/200908/t20090802_9330086.shtml" else {
            return nil
        }
        return URL(string: "https://www.bmeia.gv.at/en/reports/austrian-representations")
    }

    func name(in language: LioLanguage) -> String {
        language.text(nameEn ?? nameZh, nameZh)
    }

    func matches(_ query: String) -> Bool {
        if let country = Self.commonCountryNames[query.lowercased()] {
            return countryZh == country
        }
        return [nameZh, nameEn, countryZh, cityZh, districtZh, districtEn]
            .compactMap { $0 }
            .contains { $0.localizedStandardContains(query) }
    }
}

enum LioConsulateDirectory {
    static func bundled() throws -> [LioConsulate] {
        guard let url = Bundle.module.url(forResource: "LioConsulateDirectory.v1", withExtension: "json") else {
            throw CocoaError(.fileNoSuchFile)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let entries = try decoder.decode([LioConsulate].self, from: Data(contentsOf: url))
        let allowedPath = "/web/lbfw_673061/lsgmd_673079/"
        guard !entries.isEmpty, Set(entries.map(\.id)).count == entries.count,
              entries.allSatisfy({ entry in
                  !entry.nameZh.isEmpty && !entry.countryZh.isEmpty && !entry.cityZh.isEmpty
                      && entry.source.scheme == "https" && entry.source.host == "www.mfa.gov.cn"
                      && entry.source.path.hasPrefix(allowedPath)
              }) else { throw CocoaError(.fileReadCorruptFile) }
        return entries
    }
}
