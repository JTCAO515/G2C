#if os(iOS)
import MapKit
import SwiftUI
import UIKit

struct LioLocalSupportView: View {
    let language: LioLanguage
    private let directory: Result<LocalSupportDirectory, any Error>
    private let draftStorage: LocalSupportDraftStorage?

    init(language: LioLanguage, draftStorage: LocalSupportDraftStorage? = nil) {
        self.language = language
        self.draftStorage = draftStorage
        self.directory = Result(catching: LocalSupportDirectory.bundled)
    }

    @AppStorage("lio.local-support.nationality") private var nationality = ""
    @Environment(\.openURL) private var openURL
    @State private var picker: LocalSupportEmbassyPicker.Mode?
    @State private var actionMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                emergency(LocalSupportDirectory.emergencyContacts)
                contacts(language.text("Help lines", "求助热线"), LocalSupportDirectory.helpContacts)
                switch directory {
                case .success(let catalog):
                    embassySection(catalog.embassies)
                case .failure:
                    Text(language.text("Embassy contacts couldn’t be loaded.", "暂时无法显示使馆联系方式。"))
                        .foregroundStyle(LioTheme.inkSecondary)
                }
                contacts(language.text("Consumer services", "消费者服务"), LocalSupportDirectory.consumerContacts)
                if let draftStorage {
                    LioLocalSupportDraftEditor(language: language, storage: draftStorage)
                }
                VStack(alignment: .leading, spacing: 6) {
                    if case .success(let catalog) = directory {
                        Text(language.text("Verified as of \(catalog.verifiedAt)", "信息核对至 \(catalog.verifiedAt)"))
                    }
                    Text(language.text("Phone services and availability may change.", "电话服务和接听情况可能变化。"))
                }
                .font(.footnote)
                .foregroundStyle(LioTheme.inkSecondary)
                #if DEBUG
                if let value = ProcessInfo.processInfo.environment["G2C_LOCAL_SUPPORT_TEST_PHONE"],
                   let test = try? LocalSupportPhone(value) {
                    Button(language.text("Test dial", "测试拨号")) { dial(test) }
                        .frame(minHeight: 44)
                        .accessibilityIdentifier("lio.support.test-dial")
                }
                #endif
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
        }
        .foregroundStyle(LioTheme.ink)
        .background(LioTheme.paper)
        .navigationTitle(language.text("Local Support", "本地协助"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
        .sheet(item: $picker) { mode in
            if case .success(let catalog) = directory {
                LocalSupportEmbassyPicker(language: language, mode: mode, embassies: catalog.embassies,
                                          nationality: $nationality, dial: dial, copy: copy)
            }
        }
        .alert(language.text("Local Support", "本地协助"), isPresented: Binding(
            get: { actionMessage != nil },
            set: { if !$0 { actionMessage = nil } }
        )) {
            Button(language.text("OK", "好"), role: .cancel) {}
        } message: {
            Text(actionMessage ?? "")
        }
    }

    private func emergency(_ contacts: [LocalSupportDirectory.Contact]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            heading(language.text("Emergency numbers", "紧急报警"))
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                ForEach(contacts) { contact in
                    Button {
                        dial(contact.phone)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Image(systemName: "phone.fill")
                                .foregroundStyle(LioTheme.danger)
                                .accessibilityHidden(true)
                            Text(contact.title.zh).font(.headline)
                            Text(contact.title.en).font(.subheadline)
                            Text(contact.phone.number).font(.title2.monospacedDigit())
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("lio.support." + contact.id)
                }
            }
        }
    }

    private func contacts(_ label: String, _ contacts: [LocalSupportDirectory.Contact]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            heading(label)
            ForEach(contacts) { contact in
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(contact.title.localized(language)).font(.headline)
                        Text(contact.phone.number).monospacedDigit()
                        if let detail = contact.detail {
                            Text(detail.localized(language))
                                .font(.subheadline)
                                .foregroundStyle(LioTheme.inkSecondary)
                        }
                    }
                    Spacer(minLength: 4)
                    Button {
                        dial(contact.phone)
                    } label: {
                        Image(systemName: "phone")
                            .frame(minWidth: 44, minHeight: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(language.text("Call", "拨打") + " " + contact.title.localized(language))
                    .accessibilityIdentifier("lio.support." + contact.id)
                }
                .padding(12)
                .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
            }
        }
    }

    private func embassySection(_ embassies: [LocalSupportDirectory.Embassy]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            heading(language.text("My embassy", "我的使馆"))
            if let embassy = embassies.first(where: { $0.countryCode == nationality }) {
                LocalSupportEmbassyCard(language: language, embassy: embassy,
                                       dial: dial, copy: copy)
            }
            if embassies.isEmpty {
                Text(language.text("Embassy contacts are unavailable.", "使馆联系方式暂不可用。"))
                    .foregroundStyle(LioTheme.inkSecondary)
            } else {
                Button(language.text("Choose your nationality", "选择你的国籍")) { picker = .nationality }
                    .frame(minHeight: 44)
                Button(language.text("All embassies", "查看所有使馆")) { picker = .all }
                    .frame(minHeight: 44)
            }
        }
    }

    private func heading(_ text: String) -> some View {
        Text(text).font(.title2.bold()).accessibilityAddTraits(.isHeader)
    }

    private func dial(_ phone: LocalSupportPhone) {
        openURL(phone.url) { accepted in
            if !accepted {
                actionMessage = language.text("This device couldn’t open the phone dialler.", "此设备无法打开拨号界面。")
            }
        }
    }

    private func copy(_ address: String) { UIPasteboard.general.string = address }
}

private struct LocalSupportEmbassyCard: View {
    let language: LioLanguage
    let embassy: LocalSupportDirectory.Embassy
    let dial: (LocalSupportPhone) -> Void
    let copy: (String) -> Void

    @State private var mapUnavailable = false

    var body: some View {
        let address = embassy.address.localized(language)
        VStack(alignment: .leading, spacing: 8) {
            Text(embassy.name.localized(language)).font(.headline)
            Text(address)
            Text(embassy.phone.number).monospacedDigit()
            Button(language.text("Call embassy", "拨打使馆总机")) { dial(embassy.phone) }
                .frame(minHeight: 44)
            if let phone = embassy.consularPhone {
                Button(language.text("Call consular assistance", "拨打领事协助") + " " + phone.number) { dial(phone) }
                    .frame(minHeight: 44)
            }
            Button(language.text("Copy address", "复制地址")) { copy(address) }
                .frame(minHeight: 44)
            Button(language.text("Open in Maps", "在地图中打开"), action: showOnMap)
                .frame(minHeight: 44)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .alert(language.text("Maps couldn’t open this address.", "地图无法打开此地址。"), isPresented: $mapUnavailable) {
            Button(language.text("Copy address", "复制地址")) { copy(address) }
            Button(language.text("OK", "好"), role: .cancel) {}
        }
    }

    private func showOnMap() {
        let coordinate = CLLocationCoordinate2D(latitude: embassy.latitude, longitude: embassy.longitude)
        let item = MKMapItem(placemark: MKPlacemark(coordinate: coordinate))
        item.name = embassy.name.localized(language)
        mapUnavailable = !item.openInMaps()
    }
}

private struct LocalSupportEmbassyPicker: View {
    enum Mode: String, Identifiable {
        case nationality, all
        var id: Self { self }
    }

    let language: LioLanguage
    let mode: Mode
    let embassies: [LocalSupportDirectory.Embassy]
    @Binding var nationality: String
    let dial: (LocalSupportPhone) -> Void
    let copy: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""

    private var filtered: [LocalSupportDirectory.Embassy] {
        embassies.filter {
            search.isEmpty || $0.country.zh.localizedStandardContains(search)
                || $0.country.en.localizedStandardContains(search)
                || $0.name.localized(language).localizedStandardContains(search)
        }.sorted { $0.country.localized(language).localizedCompare($1.country.localized(language)) == .orderedAscending }
    }

    var body: some View {
        NavigationStack {
            List(filtered) { embassy in
                if mode == .nationality {
                    Button {
                        nationality = embassy.countryCode
                        dismiss()
                    } label: {
                        Text(embassy.country.localized(language)).frame(minHeight: 44)
                    }
                } else {
                    NavigationLink(embassy.country.localized(language)) {
                        ScrollView {
                            LocalSupportEmbassyCard(language: language, embassy: embassy,
                                                   dial: dial, copy: copy)
                                .padding()
                        }
                        .navigationTitle(embassy.country.localized(language))
                    }
                }
            }
            .searchable(text: $search, prompt: language.text("Search countries", "搜索国家"))
            .navigationTitle(mode == .nationality
                             ? language.text("Choose your nationality", "选择你的国籍")
                             : language.text("All embassies", "查看所有使馆"))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Close", "关闭")) { dismiss() }
                }
            }
        }
    }
}
#endif
