import Foundation
import Testing
import CJAPI
@testable import CJFeedbackClient

@Suite @MainActor struct IndependentFeedbackBoundaryTests {
    @Test func emptyPendingLastBindingDirectoryReplacementFailsClosed() throws {
        let h=try Harness();defer{h.clean()}
        let moved=h.root.appendingPathExtension("independent-retained");defer{try? FileManager.default.removeItem(at:moved)}
        let client=try h.client(Interceptor {_,_,_ in Reply(text:nullResponse)})
        let op=try client.begin(binding:h.binding);var calls=0;var movedRoot=false
        h.onBinding={
            calls+=1
            if calls==3 {
                try! FileManager.default.moveItem(at:h.root,to:moved)
                try! FileManager.default.createDirectory(at:h.root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
                movedRoot=true
            }
        }
        #expect(throws:FeedbackFailure.storageUnavailable){try client.pending(operation:op)}
        #expect(movedRoot)
    }
    @Test func prepareCallbackMustNotDisplayNewDraftAsOldSubmittedContent() async throws {
        let h=try Harness();defer{h.clean()}
        let wire=Interceptor {_,bytes,_ in
            let action=try JSONDecoder().decode(Components.Schemas.FeedbackAction.self,from:bytes)
            let original=try FeedbackPending(problem:action.problem,expectation:action.expectation,context:nil,actionID:action.action_id)
            return Reply(text:try receiptJSON(original,hash:digest(bytes)))
        }
        let model=FeedbackPresentation(client:try h.client(wire));model.replace(binding:h.binding)
        model.edit(problem:"first voluntary problem",expectation:"first expectation")
        h.onBinding={h.onBinding=nil;model.edit(problem:"newer voluntary problem",expectation:"newer expectation")}
        if let work=model.prepareSubmit() {
            let original=try #require(model.original);let action=try original.action()
            #expect(model.problem==action.problem && model.expectation==action.expectation,
                "Prepared original differs from the editable fields accepted during binding callback")
            await model.perform(work)
            if model.state == .submitted {
                #expect(model.problem==action.problem && model.expectation==action.expectation,
                    "Submitted status is shown alongside text that was not submitted")
            }
        } else {
            #expect(model.problem=="newer voluntary problem" && model.original==nil)
        }
    }
}
