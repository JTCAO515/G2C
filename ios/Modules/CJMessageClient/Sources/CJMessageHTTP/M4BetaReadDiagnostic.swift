#if DEBUG && os(iOS) && !targetEnvironment(simulator) && G2C_M4_DEVICE_ACCEPTANCE
import Foundation
import CJMessageClient

/// Test-only, bounded local stages. Async URLSession completion-handler tasks
/// need not call the session's task-completion delegate; record at the actual
/// awaited boundary. Never records request queries, headers, bodies or tokens.
enum M4BetaReadDiagnostic {
    static func record(endpoint:URL,path:String,stage:String,status:Int?=nil,error:(any Error)?=nil) {
        let environment=ProcessInfo.processInfo.environment
        guard environment["G2C_M4_BETA_API"] == "1",endpoint.host=="api-beta.go2china.space",
              let id=environment["G2C_M4_BETA_DIAGNOSTIC_ID"],UUID(uuidString:id)?.uuidString==id,
              ["/v5/message-history","/v6/run-display"].contains(path) else {return}
        let category:String
        switch error {
        case nil:category="none"
        case MessageHTTPFailure.invalidResponse?:category="invalid_response"
        case MessageHTTPFailure.exchangeUnknown?:category="exchange_unknown"
        case RecoveryError.inactive?:category="inactive"
        case is DecodingError:category="decoding"
        case is URLError:category="url"
        default:category="other"
        }
        let failure=error as NSError?
        let value:[String:Any]=["diagnostic_id":id,"path":path,"stage":stage,"error_kind":category,
            "status":status as Any? ?? NSNull(),"error_code":failure?.code as Any? ?? NSNull()]
        do {
            let root=try FileManager.default.url(for:.cachesDirectory,in:.userDomainMask,appropriateFor:nil,create:true)
            let route=path=="/v6/run-display" ? "v6":"v5",kind=stage=="transport" ? "transport":"client"
            try JSONSerialization.data(withJSONObject:value).write(to:root.appendingPathComponent("G2CM4BetaRead-"+route+"-"+kind+".json"),options:.atomic)
        } catch {print("M4_BETA_READ_DIAGNOSTIC_UNAVAILABLE")}
    }
}
#endif
