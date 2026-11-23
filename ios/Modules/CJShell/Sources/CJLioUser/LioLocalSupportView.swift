#if os(iOS)
import CJRunClient
import MapKit
import SwiftUI
import UIKit

struct LioLocalSupportView: View {
    let language: LioLanguage
    let directory: LocalSupportDirectory?

    @AppStorage("lio.local-support.nationality") private var nationality = ""
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.openURL) private var openURL
    @State private var selectingNationality = false
    @State private var actionMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let directory {
                    emergency(directory.emergency)
                    contacts(language.text("Help lines", "求助热线"), directory.hotlines)
                    embassySection(directory.embassies)
                    contacts(language.text("Consumer services", "消费者服务"), directory.consumer)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(language.text("Verified as of \(directory.verifiedAt)", "信息核对至 \(directory.verifiedAt)"))
                        Text(language.text("Phone services and availability may change.", "电话服务和接听情况可能变化。"))
                    }
                    .font(.footnote)
                    .foregroundStyle(LioTheme.inkSecondary)
                } else {
                    Text(language.text("The phone directory is unavailable.", "电话目录暂不可用。"))
                }
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
        .toolbarBackground(LioTheme.paper, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(colorScheme, for: .navigationBar)
        .toolbar(.hidden, for: .tabBar)
        .toolbar {
            ToolbarItem(placement: .principal) {
                RunReadableText(text: language.text("Local Support", "本地协助"), style: .headline, color: LioTheme.ink)
                    .fixedSize()
                    .accessibilityAddTraits(.isHeader)
            }
        }
        .sheet(isPresented: $selectingNationality) {
            LocalSupportEmbassyPicker(language: language, embassies: directory?.embassies ?? [],
                                      nationality: $nationality)
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
                            .frame(minWidth: 46, minHeight: 46)
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
            let selection = embassies.first { $0.countryCode == nationality }
            if let selection {
                LocalSupportEmbassyCard(language: language, embassy: selection, dial: dial, copy: copy)
            }
            if embassies.isEmpty {
                Text(language.text("Embassy contacts are unavailable.", "使馆联系方式暂不可用。"))
                    .foregroundStyle(LioTheme.inkSecondary)
            } else {
                Button(selection == nil
                       ? language.text("Choose your nationality", "选择你的国籍")
                       : language.text("Change nationality", "更改国籍")) {
                    selectingNationality = true
                }
                .frame(minHeight: 44)
                .accessibilityIdentifier("lio.support.nationality")
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
        VStack(alignment: .leading, spacing: 8) {
            Text(embassy.name.localized(language)).font(.headline)
            if let address = embassy.address {
                Text(address.localized(language))
            }
            if let phone = embassy.phone {
                Text(phone.number).monospacedDigit()
                Button(language.text("Call embassy", "拨打使馆总机")) { dial(phone) }
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("lio.support.embassy.call")
            } else {
                Text(language.text("An embassy switchboard number is unavailable.", "暂无可核实的使馆总机号码。"))
                    .foregroundStyle(LioTheme.inkSecondary)
            }
            if let phone = embassy.consularPhone {
                Button(language.text("Call consular assistance", "拨打领事协助") + " " + phone.number) { dial(phone) }
                    .frame(minHeight: 44)
            }
            if let address = embassy.address {
                Button(language.text("Copy address", "复制地址")) { copy(address.zh) }
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("lio.support.embassy.copy-address")
                if let latitude = embassy.latitude, let longitude = embassy.longitude {
                    Button(language.text("Open in Maps", "在地图中打开")) {
                        showOnMap(CLLocationCoordinate2D(latitude: latitude, longitude: longitude))
                    }
                    .frame(minHeight: 44)
                } else {
                    Text(language.text("Map location is unavailable. You can copy the address.",
                                       "暂无地图定位，可以复制地址。"))
                        .font(.footnote)
                        .foregroundStyle(LioTheme.inkSecondary)
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LioTheme.surface, in: RoundedRectangle(cornerRadius: LioTheme.Radius.card))
        .alert(language.text("Maps couldn’t open this address.", "地图无法打开此地址。"), isPresented: $mapUnavailable) {
            if let address = embassy.address {
                Button(language.text("Copy address", "复制地址")) { copy(address.zh) }
            }
            Button(language.text("OK", "好"), role: .cancel) {}
        }
    }

    private func showOnMap(_ coordinate: CLLocationCoordinate2D) {
        let item = MKMapItem(placemark: MKPlacemark(coordinate: coordinate))
        item.name = embassy.name.localized(language)
        mapUnavailable = !item.openInMaps()
    }
}

private struct LocalSupportEmbassyPicker: View {
    let language: LioLanguage
    let embassies: [LocalSupportDirectory.Embassy]
    @Binding var nationality: String
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
                Button {
                    nationality = embassy.countryCode
                    dismiss()
                } label: {
                    Text(embassy.country.localized(language)).frame(minHeight: 44)
                }
                .accessibilityIdentifier("lio.support.country." + embassy.countryCode)
            }
            .searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always),
                        prompt: language.text("Search countries", "搜索国家"))
            .navigationTitle(language.text("Choose your nationality", "选择你的国籍"))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(language.text("Close", "关闭")) { dismiss() }
                }
            }
        }
    }
}
#endif
