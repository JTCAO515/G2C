#if os(iOS)
import SwiftUI

struct LioConsulateDirectoryView: View {
    let language: LioLanguage
    @State private var search = ""
    private let directory = Result { try LioConsulateDirectory.bundled() }

    var body: some View {
        List {
            switch directory {
            case .success(let entries):
                let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
                let matches = query.isEmpty ? entries : entries.filter { $0.matches(query) }
                if matches.isEmpty {
                    Text(language.text("No matching consulates. Try another country, city or district.",
                                       "没有找到匹配的总领馆，请换一个国家、城市或领区。"))
                        .foregroundStyle(LioTheme.inkSecondary)
                }
                ForEach(matches) { entry in
                    NavigationLink {
                        LioConsulateDetailView(entry: entry, language: language)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(entry.name(in: language))
                                .foregroundStyle(LioTheme.ink)
                            if language == .english, entry.nameEn != nil {
                                Text(entry.nameZh).font(.subheadline).foregroundStyle(LioTheme.inkSecondary)
                            }
                        }
                        .frame(minHeight: 44, alignment: .leading)
                    }
                    .accessibilityIdentifier("lio.support.consulate." + entry.source.lastPathComponent)
                }
            case .failure:
                Text(language.text("Consulate information is unavailable.", "暂时无法显示总领馆目录。"))
                    .foregroundStyle(LioTheme.inkSecondary)
            }
        }
        .searchable(text: $search, prompt: language.text("Country, city or district", "国家、城市或领区"))
        .navigationTitle(language.text("Consulates General", "总领馆"))
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct LioConsulateDetailView: View {
    let entry: LioConsulate
    let language: LioLanguage

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(entry.name(in: language))
                    .font(.title2.bold())
                    .accessibilityAddTraits(.isHeader)

                Link(destination: entry.source) {
                    Label(language.text("Official directory entry", "外交部目录原文"), systemImage: "arrow.up.right")
                        .foregroundStyle(LioTheme.ink)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("lio.support.consulate.source")

                if let address = language == .english ? entry.addressEn ?? entry.addressZh : entry.addressZh {
                    Text(language.text("Address", "地址")).font(.headline)
                    Text(address)
                }

                Text(language.text("Consular district", "领区")).font(.headline)
                Text(language == .english
                     ? entry.districtEn ?? entry.districtZh ?? "Check the official directory for the consular district."
                     : entry.districtZh ?? "请在外交部目录确认领区。")
                    .foregroundStyle(LioTheme.inkSecondary)
                    .accessibilityIdentifier("lio.support.consulate.district")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationBarTitleDisplayMode(.inline)
    }
}
#endif
