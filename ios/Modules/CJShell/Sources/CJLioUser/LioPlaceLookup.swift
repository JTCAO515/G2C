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

/// The production lookup until the library has reviewed entries: it knows no place, so a canvas point keeps only its
/// name and coordinate and its `placeID` stays nil.
struct LioNoPlaceLookup: LioPlaceLookup {
    func match(name: String, city: String?) -> LioPlaceMatch? { nil }
}

enum LioPlaceLookups {
    /// The lookup a build uses. Release and Beta: none yet. The Debug development pack (`LioDevPlacesPack`, #if DEBUG)
    /// is layered on here once it is merged; nothing else reads the pack.
    static var standard: any LioPlaceLookup { LioNoPlaceLookup() }
}
