import Foundation
import Testing
@testable import CJLioUser

/// #1573: one tap to get back to the hotel. The hotel is kept on this device in the account's folder.
@MainActor struct LioReturnHotelTests {
    private let place = LioTaxiPlace(nameZH: "北京王府井希尔顿酒店", nameEN: "Hilton Beijing Wangfujing",
                                     addressZH: "北京市东城区王府井东街8号", addressEN: "8 Wangfujing East St",
                                     coordinate: .init(latitude: 39.9139, longitude: 116.4143, referenceSystem: .gcj02))

    private func folder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("return-hotel-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    @Test func savedHotelComesBackWithItsRoomNumber() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioReturnHotelStore(directory: LioReturnHotelStore.storageDirectory(inMessageDirectory: directory),
                                        isCurrent: { true })
        #expect(try store.load() == nil)
        let hotel = LioStayHotel(place: place, roomNumber: "1208", source: .hotelSearch)
        try store.save(hotel)
        #expect(try store.load() == hotel)
        let folder = directory.appendingPathComponent(LioReturnHotelStore.directoryName, isDirectory: true)
        #expect(try FileManager.default.contentsOfDirectory(atPath: folder.path) == [LioReturnHotelStore.fileName])
        try store.clear()
        #expect(try store.load() == nil)
    }

    @Test func anotherAccountCannotReadOrWriteTheHotel() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        var current = true
        let store = LioReturnHotelStore(directory: directory, isCurrent: { current })
        try store.save(LioStayHotel(place: place, roomNumber: nil, source: .manual))
        current = false
        #expect(throws: CancellationError.self) { try store.load() }
        #expect(throws: CancellationError.self) { try store.save(LioStayHotel(place: place, roomNumber: nil, source: .manual)) }
        #expect(throws: CancellationError.self) { try store.clear() }
    }

    @Test func aDamagedOrNewerFileReadsAsNoHotel() throws {
        let directory = try folder()
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = LioReturnHotelStore(directory: directory, isCurrent: { true })
        try Data("not json".utf8).write(to: directory.appendingPathComponent(LioReturnHotelStore.fileName))
        #expect(try store.load() == nil)
        try Data(#"{"version":99}"#.utf8).write(to: directory.appendingPathComponent(LioReturnHotelStore.fileName))
        #expect(try store.load() == nil)
    }

    @Test func roomNumberIsTrimmedAndCapped() {
        #expect(LioStayHotel(place: place, roomNumber: "  1208 ", source: .manual).roomNumber == "1208")
        #expect(LioStayHotel(place: place, roomNumber: "  ", source: .manual).roomNumber == nil)
        #expect(LioStayHotel(place: place, roomNumber: String(repeating: "9", count: 50), source: .manual)
            .roomNumber?.count == LioStayHotel.maximumRoomNumberLength)
    }

    @Test func tripPlacesThatLookLikeHotelsComeFirst() {
        func p(_ zh: String, _ en: String) -> LioTaxiPlace {
            LioTaxiPlace(nameZH: zh, nameEN: en, addressZH: nil,
                         coordinate: .init(latitude: 39.9, longitude: 116.4, referenceSystem: .gcj02))
        }
        let places = [p("故宫博物院", "The Palace Museum"), p("北京饭店", "Beijing Hotel"),
                      p("南锣鼓巷", "Nanluoguxiang"), p("胡同里客栈", "Hutong Inn"), p("全聚德", "Quanjude")]
        let ordered = LioReturnHotel.candidates(from: places).map(\.nameZH)
        #expect(ordered == ["北京饭店", "胡同里客栈", "故宫博物院", "南锣鼓巷", "全聚德"])
    }

    @Test func returnActionsUseTheTaxiPlaceAndTheDriverSign() {
        let hotel = LioStayHotel(place: place, roomNumber: "1208", source: .trip)
        #expect(hotel.place == place)
        let sign = hotel.driverSign
        #expect(sign.mainZH == "北京王府井希尔顿酒店")
        #expect(sign.leadZH == "请送我回这家酒店")
        #expect(sign.detailsZH == ["北京市东城区王府井东街8号"])
        #expect(sign.english == ["Hilton Beijing Wangfujing"])
        #expect(hotel.showCardHotel == LioShowCardInput.Hotel(nameZH: "北京王府井希尔顿酒店",
                                                                addressZH: "北京市东城区王府井东街8号"))
    }

    @Test func featureIsOffUnlessTheBuildSaysYes() {
        #expect(LioShowCardFeature.enabled(infoValue: nil) == false)
        #expect(LioShowCardFeature.enabled(infoValue: "NO") == false)
        #expect(LioShowCardFeature.enabled(infoValue: "") == false)
        #expect(LioShowCardFeature.enabled(infoValue: "YES") == true)
        #expect(LioShowCardFeature.enabled(infoValue: true) == true)
        #expect(LioShowCardFeature.enabled(infoValue: false) == false)
    }

    @Test func lioRecognisesAskingToGoBackToTheHotel() {
        for text in ["回酒店", "我要回酒店", "怎么回酒店？", "带我回宾馆", "Take me back to my hotel",
                     "back to hotel", "How do I get back to the hotel?"] {
            #expect(LioReturnHotel.isReturnRequest(text), "\(text)")
        }
        for text in ["推荐酒店", "find a hotel near the Bund", "酒店早餐几点", "hotel prices in Shanghai"] {
            #expect(!LioReturnHotel.isReturnRequest(text), "\(text)")
        }
    }
}
