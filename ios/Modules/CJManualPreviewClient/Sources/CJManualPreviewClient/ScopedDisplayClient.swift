import Foundation
import CJTripClient
import CJMessageHTTP
import OpenAPIRuntime
import HTTPTypes

@MainActor public final class ScopedDisplayRead {
    public let value: ScopedResultDisplay
    fileprivate let owner: UUID
    fileprivate let validate: @MainActor () throws -> Void
    fileprivate init(value: ScopedResultDisplay, owner: UUID, validate: @escaping @MainActor () throws -> Void) {
        self.value=value;self.owner=owner;self.validate=validate
    }
}

/// Original-result GET only. No action IDs, journals, model calls or write API.
@MainActor public final class ScopedDisplayClient {
    private let endpoint: MessageEndpoint
    private let binding: TripBinding
    private let credentials: TripCredentialCallback
    private let validate: @MainActor () throws -> Void
    private let factory: @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport
    private let owner=UUID()
    public convenience init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
                            validate: @escaping @MainActor () throws -> Void) throws {
        try self.init(endpoint:endpoint,binding:binding,credentials:credentials,validate:validate,
            factory:{ try ScopedTransport(endpoint:endpoint,profile:.scopedDisplay,validate:$0) })
    }
    convenience init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
                     validate: @escaping @MainActor () throws -> Void, transport: any ClientTransport) throws {
        try self.init(endpoint:endpoint,binding:binding,credentials:credentials,validate:validate,factory:{ _ in transport })
    }
    private init(endpoint: MessageEndpoint, binding: TripBinding, credentials: @escaping TripCredentialCallback,
                 validate: @escaping @MainActor () throws -> Void,
                 factory: @escaping @MainActor (@escaping @MainActor @Sendable () throws -> Void) throws -> any ClientTransport) throws {
        guard endpoint.maximumResponseBytes <= 4_000_000 else { throw PreviewFailure.invalidInput }
        self.endpoint=endpoint;self.binding=binding;self.credentials=credentials;self.validate=validate;self.factory=factory
        try check()
    }
    private func check() throws { try validate();try Task.checkCancellation() }
    public func read(pointer: RunScopedResultReference, original: MessageEditReference,
                     validateOriginal: @escaping @MainActor () throws -> Void) async throws -> ScopedDisplayRead {
        func current() throws { try check();try validateOriginal();try check() }
        try current()
        guard pointer.messageID.utf8.elementsEqual(original.messageID.utf8),pointer.runID.utf8.elementsEqual(original.runID.utf8),pointer.inputSHA256 == original.inputSHA256 else { throw PreviewFailure.invalidInput }
        var parts=URLComponents();parts.path="/v1/trip-scoped-results";parts.queryItems=[.init(name:"result_id",value:pointer.resultID)]
        guard let path=parts.string else { throw PreviewFailure.invalidInput }
        let bearer=try await credentials(binding)
        try current()
        guard let bearer,!bearer.isEmpty,bearer.utf8.allSatisfy({$0>32 && $0<127}) else { throw PreviewFailure.unavailable }
        var request=HTTPRequest(method:.get,scheme:nil,authority:nil,path:path)
        request.headerFields[.authorization]="Bearer "+bearer;request.headerFields[.accept]="application/json"
        let transport=try factory { [self] in try check();try validateOriginal();try check() }
        try current()
        let (response,body)=try await transport.send(request,body:nil,baseURL:endpoint.url,operationID:"readScopedDisplayV1")
        try current()
        guard !(300..<400).contains(response.status.code),let body else { throw PreviewFailure.invalidResponse }
        let bytes=try await Data(collecting:body,upTo:endpoint.maximumResponseBytes)
        try current()
        let traces=response.headerFields.filter {$0.name.canonicalName=="x-request-id"},caches=response.headerFields.filter {$0.name == .cacheControl},media=response.headerFields.filter {$0.name == .contentType}
        guard traces.count==1,let trace=traces.first?.value,UUID(uuidString:trace) != nil,caches.count==1,caches[0].value.lowercased()=="no-store",
              media.count==1,media[0].value.split(separator:";").first?.lowercased()=="application/json" else { throw PreviewFailure.invalidResponse }
        guard response.status.code==200 else { throw PreviewFailure.rejected(response.status.code) }
        let value=try ScopedResultDisplay.decode(bytes,requestID:trace,pointer:pointer,original:original)
        try current()
        return .init(value:value,owner:owner,validate:validateOriginal)
    }
    public func validateRead(_ read: ScopedDisplayRead) throws {
        guard read.owner==owner else { throw PreviewFailure.retired }
        try check();try read.validate();try check()
    }
}
