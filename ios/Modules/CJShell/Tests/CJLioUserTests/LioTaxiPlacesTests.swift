import Foundation
import Testing
@testable import CJLioUser

struct LioTaxiPlacesTests {
    @MainActor @Test func retiredSessionCannotReadOrRecreateTaxiRecents() throws {
        let place = LioTaxiPlace(nameZH: "示例地点", nameEN: "Example", addressZH: nil,
                                 coordinate: .init(latitude: 39.9, longitude: 116.4, referenceSystem: .gcj02))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let retired = LioTaxiRecentPlaces(directory: directory, isCurrent: { false })
        #expect(throws: CancellationError.self) { try retired.load() }
        #expect(throws: CancellationError.self) { try retired.record(place) }
        #expect(!FileManager.default.fileExists(atPath: directory.path))
    }

    @Test func lateTaxiReplyCannotReplaceAnotherRouteOrOpenItsLink() throws {
        let pickup = LioTaxiPlace(nameZH: "示例起点", nameEN: "Pickup", addressZH: nil,
                                  coordinate: .init(latitude: 39.9, longitude: 116.4, referenceSystem: .wgs84))
        let destination = LioTaxiPlace(nameZH: "示例终点", nameEN: "Destination", addressZH: nil,
                                       coordinate: .init(latitude: 40.05, longitude: 116.3, referenceSystem: .gcj02))
        let firstRoute = LioTaxiRoute(pickup: pickup, destination: destination)
        let differentRoute = LioTaxiRoute(pickup: destination, destination: pickup)
        var requests = LioTaxiRequestState()
        requests.start(.handoff, route: firstRoute)
        let original = try #require(requests.current)
        #expect(requests.accepts(original, route: firstRoute))
        #expect(!requests.accepts(original, route: differentRoute))
        requests.retire()
        #expect(!requests.accepts(original, route: firstRoute))
        requests.start(.handoff, route: firstRoute)
        let replacement = try #require(requests.current)
        #expect(!requests.accepts(original, route: firstRoute))
        #expect(requests.accepts(replacement, route: firstRoute))
    }

    #if DEBUG
    @MainActor @Test func fixtureHandlesLinkWithoutOpeningAnExternalApp() async throws {
        let service = LioTaxiService.preview()
        let pickup = try await service.currentPickup()
        let matches = try await service.search("Summer Palace")
        let destination = try #require(matches.first)
        #expect(try await service.search("新建宫门路").first == destination)
        let route = LioTaxiRoute(pickup: pickup, destination: destination)
        #expect(pickup.coordinate.referenceSystem == .wgs84)
        #expect(destination.coordinate.referenceSystem == .gcj02)
        #expect(try await service.estimate(route).count == 2)
        let link = try await service.rideLink(route)
        #expect(link.host == "example.invalid")
        #expect(try await service.openRideLink(link))
        #expect(try await !LioTaxiService.preview(.missingApp).openRideLink(link))
    }
    #endif

    @Test func taxiDestinationUsesOnlyTheOriginalValidatedTripPoint() throws {
        let location = LioItinerary.Point(latitude: 39.98317, longitude: 116.31056)
        let matched = LioRichItinerary.Place(nameZH: "颐和园", nameEN: "Summer Palace", address: "新建宫门路19号",
                                             matched: true, point: location)
        let taxi = try #require(LioTaxiPlace(itineraryPlace: matched))
        #expect(taxi.coordinate.referenceSystem == .gcj02)
        #expect(taxi.coordinate.latitude == location.latitude)
        #expect(taxi.coordinate.longitude == location.longitude)
        #expect(taxi.addressZH == "新建宫门路19号")

        let missing = LioRichItinerary.Place(nameZH: "市区", nameEN: "City centre", address: nil,
                                             matched: true, point: nil)
        let unmatched = LioRichItinerary.Place(nameZH: "未匹配地点", nameEN: "Unmatched", address: nil,
                                               matched: false, point: location)
        #expect(LioTaxiPlace(itineraryPlace: missing) == nil)
        #expect(LioTaxiPlace(itineraryPlace: unmatched) == nil)
    }

    @MainActor @Test func recentsKeepMostRecentTenAndPersistOriginalChineseAddress() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = LioTaxiRecentPlaces(directory: folder)
        #expect(try store.load().isEmpty)
        let places = (0..<12).map { index in
            LioTaxiPlace(nameZH: "地点\(index)", nameEN: "Place \(index)", addressZH: "路\(index)号",
                         coordinate: .init(latitude: 39.9, longitude: 116.4, referenceSystem: .gcj02))
        }
        for place in places { _ = try store.record(place) }
        #expect(try store.load() == Array(places.suffix(10).reversed()))
        _ = try store.record(places[5])
        let reopened = try LioTaxiRecentPlaces(directory: folder).load()
        #expect(reopened.count == 10)
        #expect(reopened.first == places[5])
        #expect(reopened.filter { $0.id == places[5].id }.count == 1)
    }
}
