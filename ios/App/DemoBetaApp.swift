#if G2C_DEMO_BETA && os(iOS)
import Foundation
import SwiftUI
import CJShell
import CJSession

private final class DemoInviteRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    nonisolated func urlSession(_ session: URLSession, task: URLSessionTask,
                                willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                                completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

enum DemoInviteClient {
    static func exchange(code: String, consent: Bool, language: DemoStarterLanguage) async throws -> SessionMaterial {
        let request: URLRequest
        do { request = try DemoBetaConfiguration.inviteRequest(code: code, consent: consent) }
        catch { throw DemoAccountExchangeFailure.rejected }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = nil
        configuration.urlCache = nil
        configuration.urlCredentialStorage = nil
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 25
        let session = URLSession(configuration: configuration, delegate: DemoInviteRedirectBlocker(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }

        do {
            let (body, http) = try await read(request, session: session)
            let grant = try DemoBetaConfiguration.verifyInviteResponse(body, status: http.statusCode,
                contentType: http.value(forHTTPHeaderField: "Content-Type"), now: Date())
            let conversations: DemoStarterReads.Conversations = try await starter("/v1/conversations",
                query: .init(name: "limit", value: "20"), grant: grant, session: session, trace: \.request_id)
            let needs: DemoStarterReads.Needs = try await starter("/v1/needs",
                query: .init(name: "needs_id", value: language.needsID), grant: grant, session: session, trace: \.request_id)
            let travel: DemoStarterReads.Travel = try await starter("/v1/travel-context-actions/" + language.travelActionID,
                grant: grant, session: session, trace: \.request_id)
            let profile = try DemoStarterReads.profile(language: language, conversations: conversations, needs: needs, travel: travel)
            try Task.checkCancellation()
            try grant.validate(now: Date())
            return try SessionMaterial(trustedSDKBytes: JSONEncoder().encode(DemoInviteSession(grant: grant, composition: profile)))
        } catch DemoBetaConfiguration.Failure.inviteDenied {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoBetaConfiguration.Failure.invalidInput {
            throw DemoAccountExchangeFailure.rejected
        } catch DemoBetaConfiguration.Failure.expired {
            throw DemoAccountExchangeFailure.expired
        } catch let failure as DemoAccountExchangeFailure {
            throw failure
        } catch {
            throw DemoAccountExchangeFailure.unavailable
        }
    }

    private static func starter<Value: Decodable>(_ path: String, query: URLQueryItem? = nil,
        grant: DemoInviteGrant, session: URLSession, trace: KeyPath<Value, String>) async throws -> Value {
        var url = URLComponents(url: DemoBetaConfiguration.endpoint, resolvingAgainstBaseURL: false)!
        url.path = path
        url.queryItems = query.map { [$0] }
        var request = URLRequest(url: url.url!)
        request.setValue("Bearer " + grant.access_token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (body, response) = try await read(request, session: session)
        if response.statusCode == 401 || response.statusCode == 403 { throw DemoAccountExchangeFailure.rejected }
        guard response.statusCode == 200,
              response.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first?.lowercased() == "application/json" else {
            throw DemoAccountExchangeFailure.unavailable
        }
        let value = try JSONDecoder().decode(Value.self, from: body)
        let requestID = value[keyPath: trace]
        guard UUID(uuidString: requestID) != nil, requestID == response.value(forHTTPHeaderField: "X-Request-ID") else {
            throw DemoAccountExchangeFailure.unavailable
        }
        return value
    }

    private static func read(_ request: URLRequest, session: URLSession) async throws -> (Data, HTTPURLResponse) {
        let (stream, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.url == request.url else { throw DemoAccountExchangeFailure.unavailable }
        var body = Data()
        for try await byte in stream {
            guard body.count < 65536 else { throw DemoAccountExchangeFailure.unavailable }
            body.append(byte)
        }
        return (body, http)
    }
}

struct DemoBetaRootView: View {
    let shell: ShellState
    let root: DevelopmentAccountRoot
    @Environment(\.scenePhase) private var phase

    var body: some View {
        Group {
            if case .signedIn = root.accounts.state {
                business
            } else if root.finishingDemoCleanup {
                business.safeAreaInset(edge: .top) {
                    if root.cleanup?.presentation.controlsFinalized == true {
                        Button(shell.language.text("Done", "完成")) { root.finishDemoCleanup() }
                            .padding().accessibilityIdentifier("demo.cleanup.done")
                    }
                }
            } else {
                DemoInviteView(shell: shell, accounts: root.accounts)
            }
        }
        .onChange(of: phase) { _, current in
            guard !root.finishingDemoCleanup else { return }
            if current == .active { root.accounts.resume() }
            else { root.accounts.suspend() }
        }
        .task(id: phase) {
            guard phase == .active else { return }
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(20)) } catch { return }
                if !root.finishingDemoCleanup { await root.accounts.recheckDemoSession() }
            }
        }
    }

    private var business: some View {
        ShellView(state: shell, messageHost: root.trip?.messages.messages,
                  serverHistoryHost: root.trip?.messages.history, typedMemoryContainerHost: root.trip?.typedMemory?.host,
                  tripContainerHost: root.trip?.trips, structuredTripHost: root.trip?.structuredTrips,
                  needsContainerHost: root.trip?.needs?.host, answerFeedbackHost: root.trip?.feedback?.answer,
                  generalFeedbackHost: root.trip?.feedback?.general, runContainerHost: root.trip?.messages.runs,
                  developmentAccountHost: root.accounts, offlineTripController: root.offline,
                  demoV2Assistant: root.trip?.messages.demoV2Assistant)
            .environment(\.accountCleanupHost, root.cleanup)
            .id(root.trip?.id)
    }
}

private struct DemoInviteView: View {
    let shell: ShellState
    let accounts: DevelopmentAccountHost
    @State private var code = ""
    @State private var consent = false
    private var language: ShellLanguage { shell.language }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker(language.text("Language", "语言"), selection: Binding(get: { language }, set: { shell.selectLanguage($0) })) {
                        Text("English").tag(ShellLanguage.english)
                        Text("简体中文").tag(ShellLanguage.chinese)
                    }
                }
                Section {
                    SecureField(language.text("Invitation code", "邀请码"), text: $code)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("demo.invite.code")
                    Toggle(language.text("I agree to use fictional trip information and omit personal data in this internal demo.",
                                         "我同意在本次内部演示中使用虚构行程信息，并不填写个人信息。"), isOn: $consent)
                        .accessibilityIdentifier("demo.invite.consent")
                    Button(language.text("Sign in", "登录")) {
                        let candidate = code
                        let agreed = consent
                        code = ""
                        let starter: DemoStarterLanguage = language == .chinese ? .zh : .en
                        accounts.signIn { try await DemoInviteClient.exchange(code: candidate, consent: agreed, language: starter) }
                    }
                    .disabled(!consent || code.isEmpty || accounts.state == .checking)
                    .accessibilityIdentifier("demo.invite.signin")
                    Button(language.text("Restore saved session", "恢复已保存的会话")) { accounts.restore() }
                        .disabled(!consent || accounts.state == .checking)
                        .accessibilityIdentifier("demo.invite.restore")
                }
                if let notice {
                    Section { Text(notice).accessibilityIdentifier("demo.invite.status") }
                }
            }
            .navigationTitle(language.text("Internal demo", "内部演示"))
        }
    }

    private var notice: String? {
        switch accounts.state {
        case .checking: language.text("Checking session…", "正在验证会话…")
        case .expired: language.text("This session has expired. Use an invitation code to sign in again.", "会话已过期，请使用邀请码重新登录。")
        case .rejected: language.text("This invitation or session is unavailable. Ask your demo organizer for access.", "邀请码或会话不可用，请联系演示组织者。")
        case .networkUnknown: language.text("Unable to verify the session right now. Try again when connected.", "暂时无法验证会话，请联网后重试。")
        case .storageUnavailable: language.text("Secure session storage is unavailable.", "安全会话存储暂不可用。")
        case .paused, .signedOut, .signedIn: nil
        }
    }
}
#endif
