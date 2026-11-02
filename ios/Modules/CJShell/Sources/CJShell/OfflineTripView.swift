#if os(iOS)
import SwiftUI
import CJOfflineTrip
import CJRunClient

struct OfflineTripEntry: View {
    let controller: OfflineTripController
    let language: ShellLanguage
    var body: some View {
        NavigationLink {
            OfflineTripView(controller: controller, language: language)
        } label: {
            RunReadableText(text: language.text("Read saved offline trip", "读取已保存的离线行程"))
                .frame(minHeight: 44)
        }.accessibilityIdentifier("offline.open")
    }
}

struct OfflineSyncLabel: View {
    let controller: OfflineTripController
    let language: ShellLanguage
    var body: some View {
        RunReadableText(text: text).accessibilityIdentifier("offline.sync.status")
    }
    private var text: String {
        switch controller.syncState {
        case .idle: language.text("No offline synchronization has been confirmed here.", "此处尚未确认离线同步。")
        case .synchronizing: language.text("Reading the formal trip for offline synchronization…", "正在读取正式行程并同步离线快照…")
        case .saved: language.text("Offline snapshot saved from this successful formal-trip read.", "已从此次成功读取的正式行程保存离线快照。")
        case .failed: language.text("Offline synchronization failed. Read the cache to check whether a previous snapshot is available.", "离线同步失败，请读取缓存核对是否仍有此前的快照。")
        case .unknown: language.text("The local write is unconfirmed. Keep the original storage state; reading may be unavailable.", "本机写入尚未核实，请保留原存储状态；当前可能无法读取。")
        }
    }
}

struct OfflineTripView: View {
    let controller: OfflineTripController
    let language: ShellLanguage
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                RunReadableText(text: language.text(
                    "Offline copy. Road conditions, opening hours and other changing information may be outdated.",
                    "离线副本，不代表最新路况、营业时间等动态信息。"))
                    .accessibilityIdentifier("offline.notice")
                RunReadableText(text: language.text("This page cannot send or queue trip changes or messages.",
                    "此页面不能发送或排队提交行程更改和消息。"))
                    .accessibilityIdentifier("offline.readOnly")
                switch controller.state {
                case .readable(let read):
                    RunReadableText(text: language.text("Saved offline snapshot", "已保存的离线快照"))
                        .accessibilityIdentifier("offline.state")
                    RunReadableText(text: read.namespace.trip).accessibilityIdentifier("offline.tripID")
                    RunReadableText(text: language.text("Formal version ", "正式版本 ") + String(read.version))
                        .accessibilityIdentifier("offline.version")
                    RunReadableText(text: language.text("Last successful sync: ", "最后成功同步：") + stamp(read.syncedAt))
                        .accessibilityIdentifier("offline.syncedAt")
                    RunReadableText(text: language.text("Readable until: ", "可读至：") + stamp(read.deadline))
                        .accessibilityIdentifier("offline.deadline")
                    RunReadableText(text: read.responseHash).accessibilityIdentifier("offline.hash")
                    switch read.content {
                    case .text(let trip):
                        RunReadableText(text: trip.document.title, style: .headline).accessibilityIdentifier("offline.title")
                        ForEach(trip.document.items, id: \.id) { item in
                            RunReadableText(text: item.text).accessibilityIdentifier("offline.item." + item.id)
                        }
                    case .structured(let trip):
                        StructuredTripDocumentView(document: trip.document, language: language, prefix: "offline.structured")
                        TripPlaceMapView(document: trip.document, language: language, allowsMap: false)
                    }
                case .idle: message(language.text("Read the saved snapshot on this device.", "读取本机保存的快照。"))
                case .missing: message(language.text("No offline snapshot is saved.", "尚未保存离线快照。"))
                case .expired: message(language.text("The offline snapshot has expired. Connect and successfully synchronize the formal trip before reading again.", "离线快照已到期，请联网成功同步正式行程后再读取。"))
                case .untrustedTime: message(language.text("The device time cannot be trusted for this snapshot. Its readable period has not been extended. Connect and synchronize again.", "设备时间无法用于核验此快照，可读期限未被延长，请联网重新同步。"))
                case .unavailable: message(language.text("This offline snapshot is unavailable for the current local session.", "当前本机会话无法读取此离线快照。"))
                case .storageFailure: message(language.text("The protected local snapshot could not be verified. Nothing is shown as successfully read.", "无法核验受保护的本机快照，未显示读取成功。"))
                }
                Button { controller.readCached() } label: {
                    RunReadableText(text: language.text("Read local cache", "读取本机缓存"))
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                }.buttonStyle(ShellReadableButtonStyle()).accessibilityIdentifier("offline.read")
            }.padding().frame(maxWidth: .infinity, alignment: .leading)
        }.clipped()
            .navigationTitle(language.text("Offline trip", "离线行程"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(uiColor: .systemBackground), for: .navigationBar, .tabBar)
            .toolbarBackground(.visible, for: .navigationBar, .tabBar)
            .task {
                controller.readCached()
                while !Task.isCancelled {
                    do { try await Task.sleep(for: .seconds(1)) } catch { return }
                    controller.checkDisplayedTime()
                }
            }
            .onDisappear { controller.hide() }
    }
    private func stamp(_ seconds: Int64) -> String {
        ISO8601DateFormatter().string(from: Date(timeIntervalSince1970: Double(seconds)))
    }
    private func message(_ text: String) -> some View {
        RunReadableText(text: text).accessibilityIdentifier("offline.state")
    }
}
#endif
