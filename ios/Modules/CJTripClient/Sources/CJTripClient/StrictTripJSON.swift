import CJStrictJSON

enum TripJSONPolicy: StrictJSONPolicy {
    static var failure: TripFailure { .invalidResponse }
}
typealias StrictTripJSON = StrictJSONReader<TripJSONPolicy>
typealias TripJSONValue = StrictJSONValue
