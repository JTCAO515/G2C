#if os(iOS)
import SwiftUI

/// Debug launch arguments for the trip home screenshots: `--lio-trip-home-preview <state>`, where the state is
/// `none`, `before`, `arrival`, `china`, `evening` or `ended`. Sample data only, kept in memory: a Beijing plan,
/// a German passport, a saved hotel, preview reminders. Arrival Mode is a stand-in that answers visa-free for
/// any dated trip, as its rules do for a German passport on these dates. Nothing is written to an account folder
/// or to the shared passport setting; the sample hotel sits in a temporary folder for Back to Hotel to read.
enum LioTripHomePreview {
    /// Always false outside Debug builds.
    static var requested: Bool {
        #if DEBUG
        ProcessInfo.processInfo.arguments.contains("--lio-trip-home-preview")
        #else
        false
        #endif
    }

    /// The preview home for the Trips tab; empty outside Debug builds.
    @MainActor static func home(language: LioLanguage, openChat: @escaping () -> Void) -> AnyView {
        #if DEBUG
        AnyView(previewHome(language: language, openChat: openChat))
        #else
        AnyView(EmptyView())
        #endif
    }
}

#if DEBUG
extension LioTripHomePreview {

    enum Scene: String, CaseIterable { case none, before, arrival, china, evening, ended }

    static var scene: Scene {
        let arguments = ProcessInfo.processInfo.arguments
        guard let index = arguments.firstIndex(of: "--lio-trip-home-preview"), index + 1 < arguments.count else { return .before }
        return Scene(rawValue: arguments[index + 1]) ?? .before
    }

    static let beijing = LioTripChecklist.beijing

    private static func at(_ text: String) -> Date {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = beijing
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter.date(from: text) ?? .now
    }

    static func now(_ scene: Scene) -> Date {
        switch scene {
        case .none, .before: at("2026-11-30 10:00")
        case .arrival: at("2026-12-08 16:00")
        case .china: at("2026-12-09 12:30")
        case .evening: at("2026-12-09 20:30")
        case .ended: at("2026-12-16 10:00")
        }
    }

    static func plan(_ language: LioLanguage) -> LioPlanSummary {
        func item(_ id: String, _ zh: String, _ en: String, _ time: String) -> LioPlanSummary.Item {
            .init(id: id, label: language.text(en, zh), startTime: time, endTime: nil, fixed: nil)
        }
        return LioPlanSummary(tripID: "preview-beijing", tripVersion: 1,
                              title: language.text("Five days in Beijing", "北京五日"), startDate: "2026-12-08", undated: false,
                              days: [
            .init(number: 1, date: "2026-12-08", items: [item("1a", "王府井大街", "Wangfujing Street", "18:00")]),
            .init(number: 2, date: "2026-12-09", items: [item("2a", "故宫博物院", "The Palace Museum", "09:00"),
                                                         item("2b", "景山公园", "Jingshan Park", "14:00"),
                                                         item("2c", "南锣鼓巷", "Nanluoguxiang", "18:30")]),
            .init(number: 3, date: "2026-12-10", items: [item("3a", "慕田峪长城", "Mutianyu Great Wall", "08:00")]),
            .init(number: 4, date: "2026-12-11", items: [item("4a", "中国国家博物馆", "National Museum of China", "10:00"),
                                                         item("4b", "天坛公园", "Temple of Heaven", "15:00")]),
            .init(number: 5, date: "2026-12-12", items: [item("5a", "颐和园", "Summer Palace", "09:30")])
        ])
    }

    static let hotel = LioStayHotel(
        place: LioTaxiPlace(nameZH: "北京王府井希尔顿酒店", nameEN: "Hilton Beijing Wangfujing",
                            addressZH: "北京市东城区王府井东街8号", addressEN: "8 Wangfujing East Street",
                            coordinate: .init(latitude: 39.9139, longitude: 116.4143, referenceSystem: .gcj02)),
        roomNumber: nil, source: .manual)

    private static func snapshot(_ scene: Scene) -> LioTripHomeStore.Snapshot {
        guard scene != .none else { return .init() }
        let profile = LioTripProfile(arrival: LioTripDay("2026-12-08"), stayDays: 7, cityID: "beijing",
                                     startedAt: at("2026-11-25 09:00"))
        let ticked: [String]
        switch scene {
        case .none: ticked = []
        case .before: ticked = ["payment"]
        case .arrival: ticked = ["entry", "payment", "medical-card", "booking.beijing.palace-museum.2026-12-09"]
        case .china, .evening, .ended:
            ticked = ["entry", "payment", "medical-card", "check-in", "booking.beijing.palace-museum.2026-12-09",
                      "booking.beijing.mutianyu.2026-12-10"]
        }
        return .init(profile: profile, ticks: LioTripTicks(done: Dictionary(uniqueKeysWithValues: ticked.map { ($0, at("2026-11-26 09:00")) })))
    }

    private static func arrivalSteps(_ scene: Scene) -> Set<String> {
        switch scene {
        case .none, .before: []
        case .arrival: ["entry", "payment", "internet"]
        case .china, .evening, .ended: ["entry", "payment", "internet", "transfer", "taxi"]
        }
    }

    @MainActor private final class Steps {
        var done: Set<String>
        init(_ done: Set<String>) { self.done = done }
    }

    @MainActor static func arrival(_ scene: Scene, _ language: LioLanguage) -> LioTripHomeArrival {
        let steps = Steps(arrivalSteps(scene))
        func page(_ title: String) -> AnyView {
            AnyView(ContentUnavailableView(title, systemImage: "airplane.arrival",
                                           description: Text(language.text("Preview: this opens Arrival Mode’s own page.",
                                                                           "预览：这里打开落地模式自己的页面。"))))
        }
        return LioTripHomeArrival(
            entry: { profile, _, _ in profile?.arrival == nil ? .missingDetails : .visaFree(maxDays: 30, checkedOn: "2026-11-25") },
            checklist: { LioTripArrivalChecklist(done: steps.done, total: 6) },
            setStep: { step, done in if done { steps.done.insert(step) } else { steps.done.remove(step) } },
            entryPage: { _ in page(language.text("Before you land", "入境前准备")) },
            internetPage: { page(language.text("Get online", "解决上网")) },
            checklistPage: { _ in page(language.text("Arrival Mode", "落地模式")) })
    }

    private struct Reminders: LioAttractionReminderCenter {
        let pending: Set<String>
        func requestAuthorization() async -> Bool { false }
        func add(_ request: LioAttractionReminder.Request) async throws {}
        func pendingIDs() async -> Set<String> { pending }
        func remove(_ id: String) async {}
    }

    private static let reminderScope = LioAttractionReminderScope(account: nil)

    @MainActor static func tools(_ scene: Scene, _ language: LioLanguage) -> LioTripHomeTools {
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("LioTripHomePreview-\(ProcessInfo.processInfo.processIdentifier)", isDirectory: true)
        let store = LioReturnHotelStore(directory: folder, isCurrent: { true })
        if [.china, .evening, .ended].contains(scene) { try? store.save(hotel) } else { try? store.clear() }
        return LioTripHomeTools(
            arrival: arrival(scene, language),
            hotelStore: store,
            showCards: true,
            reminders: LioAttractionReminderScheduler(
                center: Reminders(pending: [reminderScope.prefix + "beijing.national-museum.2026-12-11"]), scope: reminderScope),
            roadbookStore: try? LioRoadbookStore.preview(),
            roadbooks: true)
    }

    @MainActor static func previewHome(language: LioLanguage, openChat: @escaping () -> Void) -> some View {
        let scene = scene
        return LioTripHome(language: language, store: nil, plans: scene == .none ? [] : [plan(language)],
                           tools: tools(scene, language), showAllTrips: {}, openChat: openChat,
                           fixedNow: now(scene), timeZone: beijing,
                           model: LioTripHomeModel(store: nil, initial: snapshot(scene)), keepsSettingsInMemory: true,
                           askLio: { _ in openChat() })
    }
}
#endif
#endif
