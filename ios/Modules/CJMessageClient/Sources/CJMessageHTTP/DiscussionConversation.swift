import Foundation
import CJAPI
import CJMessageClient
import OpenAPIRuntime
import HTTPTypes

public struct DiscussionConversationWork:Sendable,CustomReflectable {
    public let conversationID:String
    fileprivate let owner:UUID
    fileprivate let lease:Lease
    fileprivate let operation:ConversationOpeningOperation
    fileprivate let creation:Bool
    public var customMirror:Mirror { Mirror(self,children:[:]) }
}
public enum DiscussionConversationOutcome:Sendable {
    case available(String),unknown,rejected(status:Int,error:Components.Schemas.ErrorResponse)
}
private struct ConversationOpeningExit:ClientTransport {
    let live:NoRedirectTransport
    let validate:@MainActor @Sendable () throws -> Void
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        try await live.sendConversationOpening(request,body:body,baseURL:baseURL,operationID:operationID,validateOriginal:validate)
    }
}
extension MessageHTTPClient {
    public func prepareNewDiscussionConversation(lease:Lease) throws -> DiscussionConversationWork {
        if let liveMessageTransport { try liveMessageTransport.validateTripDiscussionSending(to:endpoint) }
        else if !submissionEnabledForTest { throw MessageHTTPFailure.productionActivationUnavailable }
        try recovery.validateScope(scope,lease:lease)
        let id="discussion."+UUID().uuidString
        let operation=try recovery.stageConversationOpening(conversationID:id,lease:lease)
        return .init(conversationID:id,owner:conversationOpeningOwner,lease:lease,operation:operation,creation:true)
    }
    public func prepareDiscussionConversationQuery(id:String,lease:Lease) throws -> DiscussionConversationWork {
        try recovery.validateScope(scope,lease:lease)
        let operation=try recovery.beginConversationOpeningQuery(conversationID:id,lease:lease)
        return .init(conversationID:id,owner:conversationOpeningOwner,lease:lease,operation:operation,creation:false)
    }
    private func validateOpening(_ work:DiscussionConversationWork) throws {
        guard work.owner==conversationOpeningOwner else { throw RecoveryError.queryOnly }
        try recovery.validateScope(scope,lease:work.lease);try recovery.validateConversationOpening(work.operation)
    }
    public func performDiscussionConversation(_ work:DiscussionConversationWork) async throws -> DiscussionConversationOutcome {
        try validateOpening(work)
        if !work.creation {
            tripDiscussionPermitState.heads.removeValue(forKey:Data(work.conversationID.utf8))
            var parts=URLComponents();parts.path="/v3/message-send-status";parts.queryItems=[.init(name:"conversation_id",value:work.conversationID)]
            guard let path=parts.string else { throw MessageHTTPFailure.invalidConfiguration }
            let (status,raw,trace)=try await versionedMessageExchange(path:path,operation:"readTripDiscussionStatusV3",raw:nil,lease:work.lease)
            try validateOpening(work)
            guard status==200 else { return .rejected(status:status,error:try JSONDecoder().decode(Components.Schemas.ErrorResponse.self,from:raw)) }
            let value=try TripDiscussionStatus(raw:raw,maximumBytes:endpoint.maximumResponseBytes,requestID:trace,conversationID:work.conversationID,original:nil)
            guard value.head != nil else { return .unknown }
            try recovery.observeConversationOpening(work.operation,phase:.available,httpStatus:200,responseUTF8:raw)
            return .available(work.conversationID)
        }
        if let liveMessageTransport { try liveMessageTransport.validateTripDiscussionSending(to:endpoint) }
        else if !submissionEnabledForTest { throw MessageHTTPFailure.productionActivationUnavailable }
        try validateOpening(work);try recovery.consumeConversationCreation(work.operation)
        do {
            let checked=try await checkedTransport(work.lease);try validateOpening(work)
            let exit:any ClientTransport
            if let liveMessageTransport { exit=ConversationOpeningExit(live:liveMessageTransport,validate:{ [self] in try validateOpening(work) }) }
            else { exit=checked.underlying } // explicit non-network module-test seam
            let bounded=CheckedTransport(underlying:exit,endpoint:endpoint,bearer:checked.bearer,validate:{ [self] in try validateOpening(work) })
            var parts=URLComponents();parts.path="/v1/conversations";parts.queryItems=[.init(name:"conversation_id",value:work.conversationID)]
            guard let path=parts.string else { throw MessageHTTPFailure.invalidConfiguration }
            var request=HTTPRequest(method:.put,scheme:nil,authority:nil,path:path);request.headerFields[.accept]="application/json"
            let (response,body)=try await bounded.send(request,body:nil,baseURL:endpoint.url,operationID:Operations.openConversation.id)
            try validateOpening(work)
            let media=response.headerFields.filter { $0.name == .contentType },controls=response.headerFields.filter { $0.name == .cacheControl }
            guard media.count==1,media[0].value.split(separator:";").first?.lowercased()=="application/json",
                  controls.count==1,controls[0].value.lowercased()=="no-store",let body else { throw MessageHTTPFailure.invalidResponse }
            let raw=try await Data(collecting:body,upTo:endpoint.maximumResponseBytes);try validateOpening(work)
            if response.status.code==200 {
                let json=try DiscussionJSON(raw,maximumBytes:endpoint.maximumResponseBytes)
                _=try DiscussionJSON.fields(json.object,"request_id conversation_id generation last_sequence")
                _=try json.integer(["last_sequence"],minimum:0)
                let value=try JSONDecoder().decode(Components.Schemas.ConversationOpenResponse.self,from:raw)
                guard DiscussionJSON.same(value.conversation_id,work.conversationID),!value.generation.isEmpty else { throw MessageHTTPFailure.invalidResponse }
                try recovery.observeConversationOpening(work.operation,phase:.available,httpStatus:200,responseUTF8:raw)
                return .available(work.conversationID)
            }
            let error=try JSONDecoder().decode(Components.Schemas.ErrorResponse.self,from:raw)
            if error.error.outcome == .failed,error.error.recovery == .do_not_retry {
                try recovery.observeConversationOpening(work.operation,phase:.failed,httpStatus:response.status.code,responseUTF8:raw)
            }
            return .rejected(status:response.status.code,error:error)
        } catch { throw MessageHTTPFailure.exchangeUnknown }
    }
}
