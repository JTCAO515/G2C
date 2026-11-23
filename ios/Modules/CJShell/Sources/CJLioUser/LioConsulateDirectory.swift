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

    var id: URL { source }

    func name(in language: LioLanguage) -> String {
        language.text(nameEn ?? nameZh, nameZh)
    }

    func matches(_ query: String) -> Bool {
        [nameZh, nameEn, countryZh, cityZh, districtZh, districtEn]
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
