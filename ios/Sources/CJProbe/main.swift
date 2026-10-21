import Foundation
import CJAPI

@main
struct ProbeCommand {
    static func main() async {
        do {
            let connection = try ProbeConnection(environment: ProcessInfo.processInfo.environment)
            switch try await connection.fetch() {
            case .connected(let body):
                print(String(decoding: try JSONEncoder().encode(body), as: UTF8.self))
            case .rejected(let status, let body):
                print("HTTP \(status)")
                print(String(decoding: try JSONEncoder().encode(body), as: UTF8.self))
                exit(1)
            }
        } catch ProbeFailure.redirectRejected(let status) {
            print("FAIL HTTP \(status) redirect rejected; destination not requested")
            exit(1)
        } catch ProbeFailure.missingLocalConfiguration {
            print("FAIL missing or invalid local configuration")
            exit(1)
        } catch {
            print("UNKNOWN connection unavailable or response invalid")
            exit(1)
        }
    }
}
