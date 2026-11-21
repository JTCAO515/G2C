import Foundation

struct LioHotelArea: Equatable, Sendable {
    let nameZH: String
    let nameEN: String
    let center: LioTaxiPlace.Coordinate
    let radiusMetres: Int
}

struct LioHotelSearch: Sendable {
    enum Scope: Equatable, Sendable {
        case city(String), area(LioHotelArea)
    }

    enum Validation: Error, Equatable {
        case cityRequired, invalidCity, checkoutMustFollowCheckin, invalidGuestCount
    }

    static let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        return calendar
    }()

    let scope: Scope
    let checkIn: String
    let checkOut: String
    let guests: Int
    let language: LioLanguage

    init(scope: Scope, checkIn: Date, checkOut: Date, guests: Int, language: LioLanguage) throws(Validation) {
        if case .city(let city) = scope {
            let trimmed = city.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { throw .cityRequired }
            guard trimmed.unicodeScalars.count <= 100,
                  !trimmed.unicodeScalars.contains(where: { $0.value < 32 }) else { throw .invalidCity }
            self.scope = .city(trimmed)
        } else {
            self.scope = scope
        }
        guard Self.calendar.compare(checkIn, to: checkOut, toGranularity: .day) == .orderedAscending else {
            throw .checkoutMustFollowCheckin
        }
        guard guests > 0 else { throw .invalidGuestCount }

        let formatter = DateFormatter()
        formatter.calendar = Self.calendar
        formatter.timeZone = Self.calendar.timeZone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        self.checkIn = formatter.string(from: checkIn)
        self.checkOut = formatter.string(from: checkOut)
        self.guests = guests
        self.language = language
    }
}

struct LioHotelLink: Sendable {
    enum Filter: String, CaseIterable, Decodable, Hashable, Sendable {
        case location, checkIn = "check_in", checkOut = "check_out", guests, language
        case acceptsForeignGuests = "accepts_foreign_guests"

        func title(_ language: LioLanguage, for scope: LioHotelSearch.Scope) -> String {
            switch self {
            case .location:
                switch scope {
                case .city: language.text("the city", "城市")
                case .area: language.text("the area", "片区")
                }
            case .checkIn: language.text("check-in", "入住日期")
            case .checkOut: language.text("checkout", "退房日期")
            case .guests: language.text("the guest count", "人数")
            case .language: language.text("the display language", "界面语言")
            case .acceptsForeignGuests: language.text("whether the hotel accepts international guests", "是否接待境外旅客")
            }
        }
    }

    let destination: URL
    let unappliedFilters: [Filter]
}

struct LioHotelService {
    let link: @MainActor (LioHotelSearch) async throws -> LioHotelLink
    let open: @MainActor (URL) async -> Bool
}

struct LioHotelFormState {
    struct Draft {
        var city = ""
        var checkIn: Date
        var checkOut: Date
        var guests = 1

        init(now: Date = Date()) {
            checkIn = now
            checkOut = LioHotelSearch.calendar.date(byAdding: .day, value: 1, to: now)!
        }
    }

    struct Operation: Identifiable {
        enum Action { case find(LioHotelSearch), open(URL) }
        let id = UUID()
        let action: Action
    }

    private(set) var draft = Draft()
    private(set) var pending: Operation?

    mutating func edit<Value: Equatable>(_ keyPath: WritableKeyPath<Draft, Value>, to value: Value) -> Bool {
        guard draft[keyPath: keyPath] != value else { return false }
        retire()
        draft[keyPath: keyPath] = value
        return true
    }

    mutating func start(_ action: Operation.Action) {
        guard pending == nil else { return }
        pending = Operation(action: action)
    }

    mutating func retire() { pending = nil }

    func accepts(_ operation: Operation) -> Bool { pending?.id == operation.id }
}

#if DEBUG
extension LioHotelService {
    static let previewArea = LioHotelArea(
        nameZH: "东城区", nameEN: "Dongcheng",
        center: .init(latitude: 39.9289, longitude: 116.4165, referenceSystem: .wgs84),
        radiusMetres: 2_000
    )

    static func preview(unapplied: [LioHotelLink.Filter] = []) -> LioHotelService {
        LioHotelService(
            link: { request in
                _ = try LioHotelWire.encode(request)
                let filters = LioHotelLink.Filter.allCases
                let missing = Set(unapplied).union([.acceptsForeignGuests])
                let path = "/v1/tools/hotel/out/fixture_handle_aaaaaaaaaaaa"
                let payload = try JSONSerialization.data(withJSONObject: [
                    "version": "HOTEL.1",
                    "url": "https://hotel.example.invalid\(path)",
                    "applied_filters": filters.filter { !missing.contains($0) }.map(\.rawValue),
                    "unapplied_filters": filters.filter { missing.contains($0) }.map(\.rawValue),
                ])
                return try LioHotelWire.readLink(payload) { $0.host == "hotel.example.invalid" && $0.path == path }
            },
            open: { _ in true }
        )
    }
}
#endif
