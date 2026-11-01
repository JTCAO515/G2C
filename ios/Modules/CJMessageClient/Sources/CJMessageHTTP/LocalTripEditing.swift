import Foundation

/// Exact local runtime routes already frozen by C. These operation labels are
/// client dispatch identities, not new server fields or permissions.
public enum LocalTripEditingOperation: String, Sendable {
    case prepare = "prepareLocalTripManualV1", save = "saveLocalTripManualV1"
    case needsPrepare = "prepareLocalTripNeedsV1", needsSave = "saveLocalTripNeedsV1"
    case initialize = "prepareLocalTripInitializationV1", initializeSave = "saveLocalTripInitializationV1"
    case queryPrepare = "queryLocalTripManualV1", queryReceipt = "queryLocalTripManualReceiptV1"
    case queryNeedsPrepare = "queryLocalTripNeedsV1", queryNeedsReceipt = "queryLocalTripNeedsReceiptV1"
    case queryInitialization = "queryLocalTripInitializationV1", queryInitializationReceipt = "queryLocalTripInitializationReceiptV1"

    public var path: String {
        switch self {
        case .prepare, .queryPrepare: "/v1/trip-manual-preparations"
        case .save: "/v1/trip-manual-saves"
        case .needsPrepare, .queryNeedsPrepare: "/v1/trip-needs-edits"
        case .needsSave: "/v1/trip-needs-saves"
        case .initialize, .queryInitialization: "/v1/trip-structured-initializations"
        case .initializeSave: "/v1/trip-structured-initialization-saves"
        case .queryReceipt: "/v1/trip-manual-receipts"
        case .queryNeedsReceipt: "/v1/trip-needs-action-receipts"
        case .queryInitializationReceipt: "/v1/trip-structured-initialization-receipts"
        }
    }
    public var queryField: String? {
        switch self {
        case .queryPrepare, .queryNeedsPrepare, .queryInitialization: "request_id"
        case .queryReceipt, .queryNeedsReceipt, .queryInitializationReceipt: "action_id"
        default: nil
        }
    }
    public var maximumRequestBytes: Int {
        switch self {
        case .save, .needsSave, .initializeSave: 32768
        default: 1_000_000
        }
    }
}
