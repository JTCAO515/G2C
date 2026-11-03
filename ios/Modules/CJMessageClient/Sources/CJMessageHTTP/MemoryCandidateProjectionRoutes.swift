import Foundation
import HTTPTypes

enum LocalMemoryCandidateProjectionRoute {
    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        if ["applyMemoryCandidateActionV1", "queryMemoryCandidateReceiptV1"].contains(operationID) {
            return LocalMemoryCandidateRoute.accepts(request, hasBody: hasBody, operationID: operationID)
        }
        guard operationID == "readMemoryCandidateProjectionV2", request.method == .get, !hasBody,
              request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path, path.utf8.count <= 65536, let parts = URLComponents(string: path),
              parts.scheme == nil, parts.host == nil, parts.fragment == nil,
              parts.percentEncodedPath == "/v6/memory-candidates", parts.percentEncodedQuery?.contains("+") == false,
              let query = parts.queryItems, query.count == 2,
              let conversation = query.first(where: { $0.name == "conversation_id" })?.value,
              let cursor = query.first(where: { $0.name == "after_candidate_id" })?.value,
              !conversation.contains("\0"), conversation.utf8.count <= 256,
              !conversation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return false }
        return cursor.isEmpty || (!cursor.contains("\0") && cursor.utf8.count <= 16384 && cursor.unicodeScalars.count <= 4096
            && !cursor.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    }
}
