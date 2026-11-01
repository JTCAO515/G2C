import CJAPI

/// Original immutable send.2 input and verified receipt association. Only the
/// MESSAGE client can issue this value; it is not a current server write permit.
public struct AcceptedTravelMessageSource: Sendable {
    public let receipt: Components.Schemas.MessageReceipt
    public let reference: Components.Schemas.MessageTravelReference
    public let creationIntent: MessageCreationIntent
    public let needsID: String?
    public let needsVersion: Int64?
}
