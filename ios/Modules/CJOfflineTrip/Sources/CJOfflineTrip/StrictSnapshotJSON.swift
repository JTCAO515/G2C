import CJStrictJSON

enum SnapshotJSONPolicy: StrictJSONPolicy {
    static var failure: OfflineFailure { .invalidSnapshot }
}
typealias StrictSnapshotJSON = StrictJSONReader<SnapshotJSONPolicy>
