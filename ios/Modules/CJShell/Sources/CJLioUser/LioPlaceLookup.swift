import Foundation

/// #1997: what the places library says about one place, as the trip canvas needs it: the library's id and, when the
/// library has one, the point. `coordinate` is GCJ-02, like every coordinate on the canvas.
struct LioPlaceMatch: Equatable, Sendable {
    let placeID: String
    let coordinate: LioTripCanvas.Coordinate?
}

/// Finds a place in the places library by the name it is known by. The canvas only knows this protocol, so the library
/// (still being reviewed, #1985 and after) can be plugged in without the canvas changing.
///
/// An implementation matches the name against the place's names and aliases in both languages, exactly (case folded),
/// and looks only inside `city` when one is given; `city` is the library's city id ("beijing", "shanghai", …).
/// A name it does not know, or knows twice, is a miss (nil): the canvas then keeps just the name and the point.
protocol LioPlaceLookup: Sendable {
    func match(name: String, city: String?) -> LioPlaceMatch?
}

/// A lookup that knows no place: a canvas point keeps only its name and coordinate and its `placeID` stays nil.
struct LioNoPlaceLookup: LioPlaceLookup {
    func match(name: String, city: String?) -> LioPlaceMatch? { nil }
}

/// Finds places in a `LioPlaceRepository` by name (#2033 follow-up). A name is matched, case-folded and exactly,
/// against a place's Chinese and English names and aliases; `city` narrows it to one library city. A name that two
/// different places answer to is a miss, never a guess. A place without a usable GCJ-02 point still matches (its id
/// is worth keeping) and carries no coordinate.
struct LioRepositoryPlaceLookup: LioPlaceLookup {
    let repository: LioPlaceRepository

    func match(name: String, city: String?) -> LioPlaceMatch? {
        let key = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !key.isEmpty else { return nil }
        var found: LioPlace?
        for place in repository.places where city == nil || place.city == city {
            let names = [place.nameZH, place.nameEN] + place.aliasesZH + place.aliasesEN
            guard names.contains(where: { $0.lowercased() == key }) else { continue }
            if let other = found, other.id != place.id { return nil }
            found = place
        }
        guard let place = found else { return nil }
        let coordinate = place.point.map { LioTripCanvas.Coordinate(latitude: $0.latitude, longitude: $0.longitude) }
        return LioPlaceMatch(placeID: place.id, coordinate: coordinate?.isValid == true ? coordinate : nil)
    }
}

enum LioPlaceLookups {
    /// The lookup a build uses: the reviewed library (`LioPlaces.v1.json`, in every build; it is not in the App yet,
    /// so until it lands nothing matches), and in a Debug build that was launched with a development pack
    /// (`--places-dev-pack`, `LioDevPlacesPack`) the pack's unreviewed places too. The hand-written samples are not
    /// used here: their coordinates are approximate and a canvas keeps what it is given.
    static var standard: any LioPlaceLookup { LioRepositoryPlaceLookup(repository: canvasRepository) }

    private static let canvasRepository = canvasRepository(library: LioPlaceRepository.resource(LioPlaceRepository.libraryResource))

    /// The places the canvas may look in. The inputs are parameters so a test can point it at a small library and pack.
    static func canvasRepository(library: Data?, arguments: [String] = ProcessInfo.processInfo.arguments,
                                 environment: [String: String] = ProcessInfo.processInfo.environment) -> LioPlaceRepository {
        #if DEBUG
        if LioDevPlacesPack.load(arguments: arguments, environment: environment) != nil {
            return LioPlaceRepository.debugRepository(library: library, samples: nil, arguments: arguments, environment: environment)
        }
        #endif
        return LioPlaceRepository(places: library.map { LioPlaceRepository.places(in: $0) } ?? [])
    }
}
