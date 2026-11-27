import Foundation
import Testing
@testable import CJLioUser

/// #2004, #2005: "Add to trip" in Stay and Explore goes to the trip canvas's "Want to go" list, by the rule of the
/// place card's (#1991): only when the canvas is on and the phone has a trip folder.
@MainActor
struct LioPlaceToolsAddToTripTests {
    private static let library = LioPlaceRepository(data: Data("""
        {"places":[
        {"id":"pl_sh_hotel","name_zh":"外滩酒店","name_en":"Bund Hotel","category":"hotel","lat":31.24,"lng":121.49},
        {"id":"pl_sh_park","name_zh":"人民公园","name_en":"People's Park","category":"attraction"}]}
        """.utf8))

    private let today: @Sendable () -> LioTripDay = { LioTripDay(date: Date(timeIntervalSince1970: 1_800_000_000), timeZone: LioTripChecklist.beijing) }

    private func store() -> (LioTripCanvasStore, URL) {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("LioPlaceToolsAdd-\(UUID().uuidString)", isDirectory: true)
        return (LioTripCanvasStore(directory: directory, isCurrent: { true }), directory)
    }

    private func plan(_ id: String) -> LioPlanSummary {
        LioPlanSummary(tripID: id, tripVersion: 1, title: id, startDate: nil, undated: true, days: [])
    }

    private func hotel() throws -> LioPlace { try #require(Self.library.place(id: "pl_sh_hotel")) }

    @Test func withTheCanvasOffOrNoTripFolderThereIsNoAddAndSoNoButton() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        #expect(LioPlaceTripAdd.toolAdder(canvasOn: false, store: store, plans: [], today: today) == nil)
        #expect(LioPlaceTripAdd.toolAdder(canvasOn: true, store: nil, plans: [], today: today) == nil)
        #expect(LioPlaceTripAdd.toolAdder(canvasOn: false, store: nil, plans: [], today: today) == nil)
        #expect(LioPlaceTripAdd.adder(canvasOn: false, store: store, plans: [], today: today) == nil)
        #expect(LioPlaceTripAdd.adder(canvasOn: true, store: nil, plans: [], today: today) == nil)
        #expect(!FileManager.default.fileExists(atPath: directory.path), "nothing is written")
    }

    @Test func addingAHotelPutsItOnTheCurrentTripsWantToGoListAndSaysYes() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        let add = try #require(LioPlaceTripAdd.toolAdder(canvasOn: true, store: store, plans: [plan("trip-1")], today: today))
        #expect(add(try hotel()))
        let canvas = try #require(try store.canvas(for: "trip-1"))
        let wish = try #require(canvas.wishlist.first)
        #expect(wish.placeID == "pl_sh_hotel" && wish.nameZH == "外滩酒店" && wish.nameEN == "Bund Hotel")
        #expect(wish.coordinate == .init(latitude: 31.24, longitude: 121.49))
        #expect(try store.canvas(for: LioTripCanvas.standaloneID) == nil, "the traveller's own canvas is not touched")
    }

    @Test func addingTheSamePlaceAgainStillSaysYesAndChangesNothing() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        let add = try #require(LioPlaceTripAdd.toolAdder(canvasOn: true, store: store, plans: [plan("trip-1")], today: today))
        #expect(add(try hotel()))
        #expect(add(try hotel()))
        #expect(try store.canvas(for: "trip-1")?.wishlist.count == 1)
        #expect(add(try #require(Self.library.place(id: "pl_sh_park"))))
        #expect(try store.canvas(for: "trip-1")?.wishlist.count == 2)
    }

    @Test func theToolPageAndThePlaceCardShareOneCanvasAndOneAnswer() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        let plans = [plan("trip-1")]
        let card = try #require(LioPlaceTripAdd.adder(canvasOn: true, store: store, plans: plans, today: today))
        let tool = try #require(LioPlaceTripAdd.toolAdder(canvasOn: true, store: store, plans: plans, today: today))
        #expect(card(try hotel()) == .added)
        #expect(tool(try hotel()), "already there counts as on the list")
        #expect(try store.canvas(for: "trip-1")?.wishlist.count == 1)
    }

    @Test func withoutASavedTripItGoesToTheTravellersOwnCanvasLikeTheCard() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        let add = try #require(LioPlaceTripAdd.toolAdder(canvasOn: true, store: store, plans: [], today: today))
        #expect(add(try hotel()))
        #expect(try store.canvas(for: LioTripCanvas.standaloneID)?.wishlist.count == 1)
    }

    @Test func aFailedWriteSaysNoSoNoAddedNoticeShows() throws {
        let (store, directory) = store()
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let file = directory.appendingPathComponent(LioTripCanvasStore.fileName)
        let newer = Data(#"{"version":99,"canvases":[]}"#.utf8)
        try newer.write(to: file)
        let add = try #require(LioPlaceTripAdd.toolAdder(canvasOn: true, store: store, plans: [plan("trip-1")], today: today))
        #expect(!add(try hotel()))
        #expect(try Data(contentsOf: file) == newer, "a canvas from a newer app is never written over")

        let stale = LioTripCanvasStore(directory: directory.appendingPathComponent("other"), isCurrent: { false })
        let addStale = try #require(LioPlaceTripAdd.toolAdder(canvasOn: true, store: stale, plans: [], today: today))
        #expect(!addStale(try hotel()))
    }

    @Test func onlyAddedAndAlreadyThereCountAsOnTheList() {
        #expect(LioPlaceTripAdd.added.isOnWantToGoList)
        #expect(LioPlaceTripAdd.alreadyThere.isOnWantToGoList)
        #expect(!LioPlaceTripAdd.failed.isOnWantToGoList)
    }
}
