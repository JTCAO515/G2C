import Foundation

struct LioLocalSupportAction: Decodable {
    private enum Version: String, Decodable {
        case localSupport = "LIO-local-support-action.1"
    }

    private enum Action: String, Decodable {
        case openSupport = "open_local_support"
    }

    enum Failure: Error, Equatable {
        case differentMessage
    }

    private let conversationID: String
    private let messageID: String
    private let action: Action?

    private enum CodingKeys: String, CodingKey {
        case version, action
        case conversationID = "conversation_id"
        case messageID = "message_id"
    }

    init(from decoder: any Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        _ = try values.decode(Version.self, forKey: .version)
        conversationID = try values.decode(String.self, forKey: .conversationID)
        messageID = try values.decode(String.self, forKey: .messageID)
        action = try values.decode(Action?.self, forKey: .action)
    }

    func opensSupport(conversationID: String, messageID: String) throws -> Bool {
        guard self.conversationID == conversationID, self.messageID == messageID else {
            throw Failure.differentMessage
        }
        return action == .openSupport
    }
}
