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
        let sign = LioShowCardContent.driver(nameZH: hotel.place.nameZH, nameEN: hotel.place.nameEN,
                                             addressZH: hotel.place.addressZH, requestZH: LioStayHotel.driverRequestZH)
        #expect(sign.mainZH == "北京王府井希尔顿酒店")
        #expect(sign.leadZH == "请送我回这家酒店")
        #expect(sign.detailsZH == ["北京市东城区王府井东街8号"])
        #expect(sign.english == ["Hilton Beijing Wangfujing"])
        #expect(LioAccountFolders.returnHotelDirectoryName == LioReturnHotelStore.directoryName)
        #expect(hotel.showCardHotel == LioShowCardInput.Hotel(nameZH: "北京王府井希尔顿酒店",
                                                                addressZH: "北京市东城区王府井东街8号"))
    }

    @Test func aSavedRoomIsCleanedWhenReadBack() throws {
        let json = #"{"place":{"nameZH":"北京饭店","nameEN":"","addressZH":null,"coordinate":{"latitude":39.9,"longitude":116.4,"referenceSystem":"gcj02"}},"roomNumber":"  0815  ","source":"manual"}"#
        let hotel = try JSONDecoder().decode(LioStayHotel.self, from: Data(json.utf8))
        #expect(hotel.roomNumber == "0815")
        #expect(hotel.place.nameEN.isEmpty, "a hotel without an English name is kept")
    }

    @Test func storesShareTheAccountFolderThatSignOutCleans() throws {
        // The Tools tab finds the message folder as the roadbook folder's parent; sign-out cleans that folder.
        let root = URL(fileURLWithPath: "/accounts/a1", isDirectory: true)
        let derived = try #require(LioReturnHotelTools.messageDirectory(roadbookDirectory:
            LioAccountFolders.roadbooks(inMessageDirectory: root)))
        #expect(derived.standardizedFileURL.path == root.standardizedFileURL.path)
        let roadbooks = LioAccountFolders.roadbooks(inMessageDirectory: root)
        let hotel = LioReturnHotelTools.hotelStore(roadbookDirectory: roadbooks, isCurrent: { true })
        #expect(hotel?.directory.path == root.appendingPathComponent("return-hotel").path)
        let details = LioReturnHotelTools.detailsStore(roadbookDirectory: roadbooks, isCurrent: { true })
        #expect(details?.directory.path == root.appendingPathComponent("show-card-details").path)
        #expect(LioReturnHotelTools.hotelStore(roadbookDirectory: nil, isCurrent: { true }) == nil)
    }

    @Test func aHotelSearchResultBecomesTheStayHotelWithItsChineseAddress() {
        let offer = LioHotelOffer(id: "h1", nameZH: "全季酒店（北京东单店）", nameEN: nil,
                                  addressZH: "北京市东城区东单北大街98号", addressEN: nil,
                                  coordinate: .init(latitude: 39.91, longitude: 116.42, referenceSystem: .gcj02),
                                  rating: nil, price: nil, metro: nil, foreignGuests: .unknown,
                                  booking: URL(string: "https://hotel.example.invalid/out/h1")!)
        let hotel = LioStayHotel(hotelSearchOffer: offer)
        #expect(hotel.source == .hotelSearch && hotel.roomNumber == nil)
        #expect(hotel.place == offer.taxiPlace)
        #expect(hotel.place.addressZH == "北京市东城区东单北大街98号")
        #expect(hotel.place.nameEN == "全季酒店（北京东单店）", "no English name: the Chinese name stands in")
    }

    private func offer(_ id: String, nameZH: String, latitude: Double) -> LioHotelOffer {
        LioHotelOffer(id: id, nameZH: nameZH, nameEN: nil, addressZH: "北京市东城区", addressEN: nil,
                      coordinate: .init(latitude: latitude, longitude: 116.42, referenceSystem: .gcj02),
                      rating: nil, price: nil, metro: nil, foreignGuests: .unknown,
                      booking: URL(string: "https://hotel.example.invalid/out/\(id)")!)
    }

    /// #1685 review: setting the same hotel again keeps the room typed on Back to Hotel; another hotel starts empty.
    @Test func settingTheSavedHotelAgainKeepsItsRoomNumber() {
        let quanji = offer("h1", nameZH: "全季酒店（北京东单店）", latitude: 39.91)
        let saved = LioStayHotel(place: quanji.taxiPlace, roomNumber: "1208", source: .manual)
        #expect(LioStayHotel(hotelSearchOffer: quanji, replacing: saved).roomNumber == "1208")
        let other = offer("h2", nameZH: "如家酒店（北京王府井店）", latitude: 39.92)
        #expect(LioStayHotel(hotelSearchOffer: other, replacing: saved).roomNumber == nil)
        #expect(LioStayHotel(hotelSearchOffer: quanji, replacing: nil).roomNumber == nil)
    }

    /// #1685 review: a failed save is shown only under the hotel that failed, and a new search starts clean
    /// from what is saved now (so a hotel changed elsewhere is not still marked as set).
    @Test func theSaveMarkBelongsToOneHotelAndANewSearchStartsFromTheSavedOne() {
        let a = offer("h1", nameZH: "全季酒店（北京东单店）", latitude: 39.91).taxiPlace.id
        let b = offer("h2", nameZH: "如家酒店（北京王府井店）", latitude: 39.92).taxiPlace.id
        var mark = LioStayHotelMark()
        mark.didFail(a)
        #expect(mark.failed(a) && !mark.failed(b))
        mark.refresh(savedHotel: nil)
        #expect(!mark.failed(a), "a new search clears the old failure")
        mark.didSave(b)
        #expect(mark.isSaved(b) && !mark.isSaved(a))
        mark.didFail(a)
        #expect(mark.failed(a) && mark.isSaved(b))
        mark.didSave(a)
        #expect(mark.isSaved(a) && !mark.isSaved(b) && !mark.failed(a))
        let elsewhere = LioStayHotel(hotelSearchOffer: offer("h2", nameZH: "如家酒店（北京王府井店）", latitude: 39.92))
        mark.refresh(savedHotel: elsewhere)
        #expect(mark.isSaved(b) && !mark.isSaved(a), "the hotel saved now wins over the one tapped earlier")
    }

    @Test func onlyAnExplicitYesTurnsTheBuildFlagOn() {
        #expect(LioShowCardFeature.enabled(infoValue: "YES"))
        for value: Any? in [nil, "", "NO", "yes", "$(G2C_SHOW_CARD_ENABLED)", true, false, 1] {
            #expect(!LioShowCardFeature.enabled(infoValue: value), "\(String(describing: value))")
        }
    }

    @Test func lioRecognisesAskingToGoBackToTheHotel() {
        for text in ["回酒店", "我要回酒店", "怎么回酒店？", "带我回宾馆", "Take me back to my hotel",
                     "back to hotel", "How do I get back to the hotel?", "Can you get me back to the hotel",
                     "bring me back to my hotel", "drive us back to our hotel", "I want to go back to my accommodation",
                     "I'm tired, back to my hotel please", "return to the hostel"] {
            #expect(LioReturnHotel.isReturnRequest(text), "\(text)")
        }
        for text in ["推荐酒店", "find a hotel near the Bund", "酒店早餐几点", "hotel prices in Shanghai",
                     "We came back from the hotel", "How do I return the hotel key?",
                     "go back to hotel search results", "back to hotel prices"] {
            #expect(!LioReturnHotel.isReturnRequest(text), "\(text)")
        }
    }
}
