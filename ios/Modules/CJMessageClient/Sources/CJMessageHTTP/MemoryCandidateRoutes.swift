import Foundation
import HTTPTypes

enum LocalMemoryCandidateRoute {
    static func accepts(_ request: HTTPRequest, hasBody: Bool, operationID: String) -> Bool {
        guard request.scheme == nil, request.authority == nil,
              !request.headerFields.contains(where: { $0.name.canonicalName == "host" }),
              let path = request.path, path.utf8.count <= 16384, let parts = URLComponents(string: path),
              parts.scheme == nil, parts.host == nil, parts.fragment == nil else { return false }
        if operationID == "applyMemoryCandidateActionV1" {
            return request.method == .post && hasBody && path == "/v3/memory-candidate-actions"
        }
        guard request.method == .get, !hasBody, let query = parts.queryItems,
              parts.percentEncodedQuery?.contains("+") == false,
              Set(query.map(\.name)).count == query.count else { return false }
        switch operationID {
        case "readMemoryCandidateJobsV1":
            guard parts.percentEncodedPath == "/v5/memory-candidate-jobs", query.count == 2,
                  let conversation = query.first(where: { $0.name == "conversation_id" })?.value,
                  let after = query.first(where: { $0.name == "after_job_id" })?.value else { return false }
            return text(conversation, bytes: 256) && (after.isEmpty || identity(after))
        case "readMemoryCandidatesV1":
            guard parts.percentEncodedPath == "/v3/memory-candidates", query.count == 2,
                  let job = query.first(where: { $0.name == "job_id" })?.value,
                  let attempt = query.first(where: { $0.name == "attempt_id" })?.value else { return false }
            return identity(job) && identity(attempt)
        case "queryMemoryCandidateReceiptV1":
            guard parts.percentEncodedPath == "/v3/memory-candidate-receipts", query.count == 1,
                  query[0].name == "action_id", let action = query[0].value else { return false }
            return identity(action)
        default: return false
        }
    }
    private static func identity(_ value: String) -> Bool { text(value, bytes: 1024) && value.unicodeScalars.count <= 256 }
    private static func text(_ value: String, bytes: Int) -> Bool {
        !value.contains("\0") && value.utf8.count <= bytes && !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}
