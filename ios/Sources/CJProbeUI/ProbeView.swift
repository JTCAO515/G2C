import SwiftUI
import CJAPI

@MainActor
public struct ProbeView: View {
    private let environment: [String: String]
    @State private var state: ProbeState = .loading
    private enum ProbeState {
        case loading
        case connected(String)
        case rejected(Int, String, String)
        case redirectRejected(Int)
        case configurationMissing
        case unavailable
    }

    public init(environment: [String: String]) { self.environment = environment }

    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("CJ Foundation").font(.title)
            Text("Local API probe · 本地接口探针").font(.headline)
            switch state {
            case .loading:
                ProgressView("Connecting · 正在连接")
            case .connected(let requestID):
                Label("Connected · 已连接", systemImage: "checkmark.circle")
                Text("BASE 1.0.0")
                Text(requestID).font(.caption.monospaced()).textSelection(.enabled)
            case .rejected(let status, let code, let requestID):
                Text("HTTP \(status) · \(code)")
                Text("Request rejected · 请求被拒绝")
                Text(requestID).font(.caption.monospaced()).textSelection(.enabled)
            case .redirectRejected(let status):
                Text("HTTP \(status) · Redirect rejected · 已拒绝重定向")
                Text("Destination not requested · 未请求跳转目标")
            case .configurationMissing:
                Text("Local configuration missing · 缺少本地配置")
            case .unavailable:
                Text("Connection unavailable or response invalid · 连接不可用或响应无效")
                Text("Outcome unknown · 结果未知")
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, alignment: .leading)
        .task { await connect() }
    }

    private func connect() async {
        let connection: ProbeConnection
        do {
            connection = try ProbeConnection(environment: environment)
        } catch {
            state = .configurationMissing
            return
        }
        do {
            let result = try await connection.fetch()
            guard !Task.isCancelled else { return }
            switch result {
            case .connected(let body): state = .connected(body.request_id)
            case .rejected(let status, let body): state = .rejected(status, body.error.code, body.request_id)
            }
        } catch ProbeFailure.redirectRejected(let status) {
            guard !Task.isCancelled else { return }
            state = .redirectRejected(status)
        } catch {
            guard !Task.isCancelled else { return }
            state = .unavailable
        }
    }
}

#Preview {
    ProbeView(environment: [:])
}
