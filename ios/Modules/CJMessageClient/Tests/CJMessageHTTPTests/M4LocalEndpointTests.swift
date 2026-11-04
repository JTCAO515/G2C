import Foundation
import Testing
@testable import CJMessageHTTP

struct M4LocalEndpointTests {
    @Test func deviceConfigurationCannotActivatePhoneLoopback() throws {
        let url = URL(string:"http://127.0.0.1:18080")!
        #if os(iOS) && !targetEnvironment(simulator) && G2C_M4_DEVICE_ACCEPTANCE
        #expect(throws:MessageHTTPFailure.self) {
            try MessageEndpoint(url:url,maximumRequestBytes:128,maximumResponseBytes:128,allowLoopbackHTTP:true)
        }
        #else
        let endpoint = try MessageEndpoint(url:url,maximumRequestBytes:128,maximumResponseBytes:128,allowLoopbackHTTP:true)
        #expect(endpoint.allowsDevelopmentActivation)
        #endif
    }
    @Test func onlyCanonicalApprovedPrivateHostsAreEligible() throws {
        for host in ["10.0.0.2", "172.16.0.2", "172.31.255.254", "192.168.1.2", "169.254.1.2"] {
            let url = try #require(URL(string: "https://" + host + ":18080"))
            #expect(MessageEndpoint.isM4LocalHTTPS(url, approvedHost: host))
            #expect(!MessageEndpoint.isM4LocalHTTPS(url, approvedHost: nil))
            #expect(!MessageEndpoint.isM4LocalHTTPS(url, approvedHost: "192.168.1.3"))
        }
        for host in ["8.8.8.8", "47.83.147.176", "172.15.0.2", "172.32.0.2", "192.169.1.2", "127.0.0.2", "0.0.0.0", "224.0.0.1", "localhost", "mac.local", "192.168.001.2"] {
            let url = try #require(URL(string: "https://" + host + ":18080"))
            #expect(!MessageEndpoint.isM4LocalHTTPS(url, approvedHost: host))
        }
        #expect(!MessageEndpoint.isM4LocalHTTPS(URL(string:"https://192.168.1.2")!,approvedHost:"192.168.1.2"))
        #expect(!MessageEndpoint.isM4LocalHTTPS(URL(string:"http://192.168.1.2:18080")!,approvedHost:"192.168.1.2"))
    }

    @Test func endpointStillRejectsCredentialPathsAndInvalidPorts() throws {
        for raw in ["http://127.0.0.1:0", "http://127.0.0.1:65536", "http://user:password@127.0.0.1:18080", "http://127.0.0.1:18080/v1", "http://127.0.0.1:18080?key=value", "http://127.0.0.1:18080#fragment"] {
            #expect(throws:MessageHTTPFailure.self) {
                try MessageEndpoint(url:URL(string:raw)!,maximumRequestBytes:128,maximumResponseBytes:128,allowLoopbackHTTP:true)
            }
        }
    }

    @Test func localNetworkNeedsTheLocalBuildFlagAndExplicitHost() throws {
        let url = URL(string:"https://192.168.1.2:18080")!
        // The flagged test invocation explicitly supplies G2C_M4_LOCAL_HOST.
        #if DEBUG && G2C_M4_DEVICE_ACCEPTANCE
        let endpoint = try MessageEndpoint(url:url,maximumRequestBytes:128,maximumResponseBytes:128,allowLoopbackHTTP:true)
        #expect(endpoint.allowsDevelopmentActivation)
        #else
        let endpoint = try MessageEndpoint(url:url,maximumRequestBytes:128,maximumResponseBytes:128,allowLoopbackHTTP:true)
        #expect(!endpoint.allowsDevelopmentActivation)
        #endif
        #expect(throws:MessageHTTPFailure.self) {
            try MessageEndpoint(url:URL(string:"http://192.168.1.2:18080")!,maximumRequestBytes:128,maximumResponseBytes:128,allowLoopbackHTTP:true)
        }
    }
}
