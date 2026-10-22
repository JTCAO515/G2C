import Foundation
import Testing
@testable import CJManualPreviewClient
@Suite @MainActor struct IndependentPreparationTests {
    @Test func olderPreparationCannotRetireNewerCallbackPreparedWork() async throws {
        let h=try Harness();try await h.load()
        let wire=Wire(try response(preview(h.original)))
        let editor=try h.editor(wire)
        var newer:PreviewWork?
        h.callback={
            h.callback=nil
            newer=try? editor.preparePreview()
        }
        _ = try? editor.preparePreview() // older caller may be cancelled/discard its work
        let work=try #require(newer)
        await editor.perform(work)
        #expect(await wire.calls.count==1,"Older preparation replaced the newer active work ID before its Task ran")
        #expect(editor.display()?.status == .local,"Newer preview was silently retired and editor stayed loading")
    }
}
