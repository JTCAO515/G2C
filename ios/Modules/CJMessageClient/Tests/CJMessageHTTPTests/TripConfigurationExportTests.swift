import Foundation
import Testing
import CJAPI
import HTTPTypes
import OpenAPIRuntime

private struct TripExportOnlyTransport: ClientTransport {
    func send(_ request:HTTPRequest,body:HTTPBody?,baseURL:URL,operationID:String) async throws -> (HTTPResponse,HTTPBody?) {
        Issue.record("Trip export smoke test must not issue requests")
        throw URLError(.unsupportedURL)
    }
}
struct TripConfigurationExportTests {
    @Test func fixedOfficialTripOperationsAreInTheSameCJAPI() throws {
        let client = Client(serverURL:try #require(URL(string:"https://synthetic.invalid")),configuration:.memory,transport:TripExportOnlyTransport())
        // Compile actual official method references only; no Trip read/write is executed.
        _ = client.actOnTripProposal
        _ = client.queryTripAction
        _ = client.listTrips
        _ = client.getTrip
        _ = client.getTripProposal
        #expect(Operations.actOnTripProposal.id == "actOnTripProposal")
        #expect(Operations.queryTripAction.id == "queryTripAction")
        #expect(Operations.listTrips.id == "listTrips")
        #expect(Operations.getTrip.id == "getTrip")
        #expect(Operations.getTripProposal.id == "getTripProposal")
    }
}
