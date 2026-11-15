import Foundation

/// The packaged release book is also the source used to export TestFlight and issue text.
public struct LioBuildUpdates: Decodable, Sendable {
    public enum Failure: Error, Sendable { case missingResource, invalidBook, unlistedBuild }
    public enum SectionID: String, Decodable, CaseIterable, Sendable {
        case changes, comparison, testing, known, service
    }
    public struct Text: Decodable, Sendable {
        public let en: String
        public let zh: String
        public func value(_ language: LioLanguage) -> String { language == .chinese ? zh : en }
    }
    public struct Items: Decodable, Sendable {
        public let en: [String]
        public let zh: [String]
        public func values(_ language: LioLanguage) -> [String] { language == .chinese ? zh : en }
    }
    public struct Section: Decodable, Sendable, Identifiable {
        public let id: SectionID
        public let title: Text
        public let items: Items
    }
    public struct Release: Decodable, Sendable {
        public let build: Int
        public let previousBuild: Int
        public let sections: [Section]
        public func whatToTest(_ language: LioLanguage) -> String {
            sections.enumerated().map { offset, section in
                "\(offset + 1). \(section.title.value(language))\n" + section.items.values(language).map { "- " + $0 }.joined(separator: "\n")
            }.joined(separator: "\n\n")
        }
    }

    public let schema: Int
    public let currentBuild: Int
    public let releases: [Release]

    public static let bundled: Result<LioBuildUpdates, Failure> = {
        guard let url = Bundle.module.url(forResource: "LioBuildUpdates.v1", withExtension: "json") else {
            return .failure(.missingResource)
        }
        do { return .success(try decode(Data(contentsOf: url))) }
        catch { return .failure(.invalidBook) }
    }()

    /// Validate the local configuration once at its decoding boundary; views then trust it.
    public static func decode(_ data: Data) throws -> LioBuildUpdates {
        let book: LioBuildUpdates
        do { book = try JSONDecoder().decode(Self.self, from: data) }
        catch { throw Failure.invalidBook }
        guard book.schema == 1, book.releases.count == 2,
              book.releases[0].build == book.currentBuild,
              book.releases[0].previousBuild == book.releases[1].build,
              book.releases.allSatisfy({ release in
                  release.build > release.previousBuild && release.previousBuild > 0
                    && release.sections.map(\.id) == SectionID.allCases
                    && release.sections.allSatisfy { section in
                        !section.title.en.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                          && !section.title.zh.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                          && !section.items.en.isEmpty && section.items.en.count == section.items.zh.count
                          && (section.items.en + section.items.zh).allSatisfy { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
                          && (section.id != .testing || (2...4).contains(section.items.en.count))
                    }
              }) else { throw Failure.invalidBook }
        return book
    }

    /// Never present another build's notes as if they belong to the installed binary.
    public func release(for build: Int) throws -> Release {
        guard let release = releases.first(where: { $0.build == build }) else { throw Failure.unlistedBuild }
        return release
    }
}
