import Foundation
import CJAPI

private enum ConsumerFailure: Error { case invalidNullBranch, expectationFailed }

@main
struct GeneratedReceiptConsumer {
    static func read(_ data: Data) throws -> String {
        let result = try JSONDecoder().decode(Components.Schemas.MessageReceiptQueryResponse.self, from: data)
        switch result.receipt {
        case .MessageReceipt(let receipt):
            guard receipt.message_id == "original", receipt.generation == "generation-original" else {
                throw ConsumerFailure.expectationFailed
            }
            return "found"
        case .case2(let value):
            // The generator uses an unvalidated container for enum:[null]. Never
            // interpret arbitrary fallback JSON as a null/not-observed receipt.
            guard value.value == nil else { throw ConsumerFailure.invalidNullBranch }
            return "not_observed"
        }
    }

    static func main() throws {
        let receipt: [String: Any] = ["message_id":"original", "conversation_id":"c", "generation":"generation-original",
                                      "sequence":1, "run_id":"run-original", "input_sha256":String(repeating:"a",count:64)]
        let requestID = "00000000-0000-4000-8000-000000000001"
        func body(_ value: Any) throws -> Data {
            try JSONSerialization.data(withJSONObject: ["request_id":requestID,"receipt":value])
        }
        guard try read(body(receipt)) == "found" else { throw ConsumerFailure.expectationFailed }
        print("PASS actual generated typed receipt is readable")
        guard try read(body(NSNull())) == "not_observed" else { throw ConsumerFailure.expectationFailed }
        print("PASS explicit null is distinct not-observed, never retry authority")
        let missing = try JSONSerialization.data(withJSONObject: ["request_id":requestID])
        do {
            _ = try read(missing)
            throw ConsumerFailure.expectationFailed
        } catch DecodingError.keyNotFound(let key, _) {
            guard key.stringValue == "receipt" else { throw ConsumerFailure.expectationFailed }
            print("PASS missing receipt throws keyNotFound, never silently null")
        }
        do {
            _ = try read(body("invalid-fallback"))
            throw ConsumerFailure.expectationFailed
        } catch ConsumerFailure.invalidNullBranch {
            print("PASS non-null fallback is explicitly invalid, never not-observed")
        }
    }
}
