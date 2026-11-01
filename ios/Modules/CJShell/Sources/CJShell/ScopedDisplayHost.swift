import Foundation
import Observation
import CJManualPreviewClient

public enum ScopedDisplayActivity: Equatable { case idle, reading, ready, unavailable, keptOriginal }
@MainActor @Observable public final class ScopedDisplayHost {
    @ObservationIgnored private weak var runs: RunContainerHost?
    @ObservationIgnored private let client: ScopedDisplayClient
    private var revision=UUID()
    private var source:ScopedDisplayRunSource?
    private var stored:ScopedDisplayRead?
    public private(set) var activity:ScopedDisplayActivity = .idle
    init(runs:RunContainerHost,client:ScopedDisplayClient) { self.runs=runs;self.client=client }
    public var busy:Bool { activity == .reading }
    public var hasResult:Bool { runs?.scopedResultMarker != nil }
    public var canRead:Bool { !busy && runs?.captureScopedDisplaySource() != nil }
    public var read:ScopedDisplayRead? {
        guard let source,let stored,source.isCurrent() else { return nil }
        do { try client.validateRead(stored) } catch { return nil }
        return source.isCurrent() ? stored : nil
    }
    public func clearSelection() { revision=UUID();source=nil;stored=nil;activity = .idle }
    public func invalidate() { clearSelection() }
    public func keepOriginal() { revision=UUID();stored=nil;source=nil;activity = .keptOriginal }
    public func prepareRead() -> (@MainActor () async -> Void)? {
        guard !busy,let captured=runs?.captureScopedDisplaySource(),let original=captured.original.editReference else { return nil }
        let token=UUID();revision=token;source=captured;stored=nil;activity = .reading
        return { [weak self] in
            guard let self else { return }
            do {
                let value=try await client.read(pointer:captured.pointer,original:original) { [weak self] in
                    guard let self,self.revision == token,captured.isCurrent(),captured.original.isStillOwned(),self.revision == token else { throw PreviewFailure.retired }
                }
                guard revision == token,captured.isCurrent() else { return }
                stored=value;activity = .ready
            } catch {
                guard revision == token else { return }
                stored=nil;activity = .unavailable
            }
        }
    }
}
