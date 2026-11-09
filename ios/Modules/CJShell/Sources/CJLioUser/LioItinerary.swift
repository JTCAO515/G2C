import Foundation

struct LioItinerary: Equatable, Identifiable, Sendable {
    struct Point: Equatable, Sendable {
        let latitude: Double
        let longitude: Double
    }

    struct Stop: Equatable, Identifiable, Sendable {
        let id: String
        let name: String
        let time: String
        let point: Point?
        let fixed: Bool
    }

    struct Day: Equatable, Identifiable, Sendable {
        let number: Int
        let stops: [Stop]
        var id: Int { number }
    }

    let id: String
    let title: String
    let description: String
    let days: [Day]
}
