import CJMessageHTTP
import CJStrictJSON
import Foundation

/// Why reading a menu did not work, in words the page can show.
enum LioMenuFailure: Error, Equatable, Sendable {
    case signInRequired, notEnabled, alreadyUsed, quota, unavailable, timedOut, offline, unreadablePhoto
}

/// MENU.1 (contracts/api/MENU.1.md): one menu photo out; checked dishes back. Nothing about the user is sent:
/// dietary needs stay on this device.
enum LioMenuWire {
    static let version = "MENU.1"
    static let route = "v1/tools/menu/explain"
    static let maximumPhoto = 3 * 1024 * 1024 - 4096
    static let maximumItems = 50
    static let maximumReply = 256 * 1024
    static let timeout: TimeInterval = 100

    private struct Request: Encodable {
        let version: String
        let requestID: String
        let media: String

        enum CodingKeys: String, CodingKey {
            case version, media
            case requestID = "request_id"
        }
    }

    static func encode(jpeg: Data, requestID: UUID) throws -> Data {
        guard jpeg.count > 3, jpeg.count <= maximumPhoto, jpeg.starts(with: [0xff, 0xd8, 0xff]) else {
            throw LioMenuFailure.unreadablePhoto
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = .sortedKeys
        return try encoder.encode(Request(version: version, requestID: requestID.uuidString.lowercased(),
                                          media: jpeg.base64EncodedString()))
    }

    private enum JSONPolicy: StrictJSONPolicy {
        static let failure = LioMenuFailure.unavailable
        static let maximumDepth = 6
        static let requiresObjectRoot = true
    }

    private static let ingredients: [String: LioMenuIngredient] = [
        "pork": .pork, "beef": .beef, "lamb": .lamb, "poultry": .poultry, "fish": .fish, "shellfish": .shellfish,
        "peanut": .peanut, "tree_nut": .treeNut, "egg": .egg, "dairy": .dairy, "gluten": .gluten, "soy": .soy,
        "sesame": .sesame, "alcohol": .alcohol, "coriander": .coriander, "animal_broth": .animalBroth,
    ]
    private static let certainties: [String: LioMenuCertainty] = ["likely": .likely, "possible": .possible]
    private static let textFields = ["summary_en", "summary_zh", "ingredients_en", "ingredients_zh", "method_en",
                                     "method_zh", "portion_en", "portion_zh"]
    private static let dishKeys = Set(["id", "kind", "name_zh", "name_en", "spice", "contains", "price_text"]
                                      + textFields)

    /// The checked reading, or `unavailable` for anything off-contract: an unexpected field, kind, ingredient,
    /// spice level or duplicate line id is never shown as a guess.
    static func read(_ data: Data) throws -> LioMenuReading {
        guard data.count <= maximumReply else { throw LioMenuFailure.unavailable }
        var reader = StrictJSONReader<JSONPolicy>(bytes: Array(data))
        do { try reader.check() } catch { throw LioMenuFailure.unavailable }
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              Set(root.keys) == ["version", "truncated", "items"], root["version"] as? String == version,
              let truncated = root["truncated"] as? Bool, isBool(root["truncated"]),
              let items = root["items"] as? [[String: Any]], items.count <= maximumItems else {
            throw LioMenuFailure.unavailable
        }
        var seen = Set<String>()
        let dishes = try items.map { item -> LioMenuDish in
            guard let id = item["id"] as? String, id.wholeMatch(of: /l[0-9]{1,2}/) != nil,
                  seen.insert(id).inserted else { throw LioMenuFailure.unavailable }
            let price = try optionalText(item["price_text"], limit: 40)
            switch item["kind"] as? String {
            case "unclear":
                guard Set(item.keys) == ["id", "kind", "price_text"] else { throw LioMenuFailure.unavailable }
                return LioMenuDish(id: id, nameZH: nil, nameEN: "", summaryEN: "", summaryZH: "", ingredientsEN: "",
                                   ingredientsZH: "", methodEN: "", methodZH: "", portionEN: "", portionZH: "",
                                   spice: nil, contains: [:], priceText: price)
            case "dish":
                return try dish(item, id: id, price: price)
            default:
                throw LioMenuFailure.unavailable
            }
        }
        return LioMenuReading(dishes: dishes, truncated: truncated)
    }

    private static func dish(_ item: [String: Any], id: String, price: String?) throws -> LioMenuDish {
        guard Set(item.keys) == dishKeys,
              let nameZH = try optionalText(item["name_zh"], limit: 60),
              let nameEN = try optionalText(item["name_en"], limit: 200),
              let rawContains = item["contains"] as? [String: Any] else {
            throw LioMenuFailure.unavailable
        }
        var texts: [String: String] = [:]
        for field in textFields {
            guard let value = item[field] as? String, value.count <= 200 else { throw LioMenuFailure.unavailable }
            texts[field] = value.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let spice: LioMenuSpice?
        if item["spice"] is NSNull {
            spice = nil
        } else {
            guard let number = item["spice"] as? NSNumber, !isBool(number), !CFNumberIsFloatType(number),
                  let known = LioMenuSpice(rawValue: number.intValue) else { throw LioMenuFailure.unavailable }
            spice = known
        }
        var contains: [LioMenuIngredient: LioMenuCertainty] = [:]
        for (key, value) in rawContains {
            guard let ingredient = ingredients[key], let text = value as? String,
                  let certainty = certainties[text] else { throw LioMenuFailure.unavailable }
            contains[ingredient] = certainty
        }
        return LioMenuDish(id: id, nameZH: nameZH, nameEN: nameEN,
                           summaryEN: texts["summary_en"]!, summaryZH: texts["summary_zh"]!,
                           ingredientsEN: texts["ingredients_en"]!, ingredientsZH: texts["ingredients_zh"]!,
                           methodEN: texts["method_en"]!, methodZH: texts["method_zh"]!,
                           portionEN: texts["portion_en"]!, portionZH: texts["portion_zh"]!,
                           spice: spice, contains: contains, priceText: price)
    }

    /// `nil` for JSON null; a non-blank string up to `limit` characters; anything else is refused.
    private static func optionalText(_ value: Any?, limit: Int) throws -> String? {
        if value is NSNull { return nil }
        guard let text = (value as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty,
              text.count <= limit else { throw LioMenuFailure.unavailable }
        return text
    }

    private static func isBool(_ value: Any?) -> Bool {
        guard let number = value as? NSNumber else { return false }
        return CFGetTypeID(number) == CFBooleanGetTypeID()
    }

    static func failure(status: Int) -> LioMenuFailure {
        switch status {
        case 401: .signInRequired
        case 403: .notEnabled
        case 409: .alreadyUsed
        case 429: .quota
        default: .unavailable
        }
    }
}

@MainActor public struct LioMenuRelayClient {
    typealias Exchange = @MainActor (URLRequest) async throws -> (Data, URLResponse)

    private let baseURL: URL
    private let isCurrent: @MainActor () -> Bool
    private let bearer: @MainActor () -> String?
    private let newRequestID: @MainActor () -> UUID
    private let exchange: Exchange

    init(baseURL: URL, isCurrent: @escaping @MainActor () -> Bool, bearer: @escaping @MainActor () -> String?,
         newRequestID: @escaping @MainActor () -> UUID = { UUID() }, exchange: @escaping Exchange) {
        self.baseURL = baseURL
        self.isCurrent = isCurrent
        self.bearer = bearer
        self.newRequestID = newRequestID
        self.exchange = exchange
    }

    func read(_ jpeg: Data) async throws -> LioMenuReading {
        try Task.checkCancellation()
        guard isCurrent(), let token = bearer(), !token.isEmpty else { throw LioMenuFailure.signInRequired }
        let url = baseURL.appending(path: LioMenuWire.route)
        // Longer than the relay's worst case (a 45 s budget plus one supplier call) so a billed reading is not
        // thrown away by the App while the server is still finishing it.
        var request = URLRequest(url: url, timeoutInterval: LioMenuWire.timeout)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.httpBody = try LioMenuWire.encode(jpeg: jpeg, requestID: newRequestID())

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await exchange(request)
        } catch {
            try requireCurrentSession()
            switch (error as? URLError)?.code {
            case .timedOut?: throw LioMenuFailure.timedOut
            case .notConnectedToInternet?, .networkConnectionLost?, .cannotFindHost?, .cannotConnectToHost?,
                 .dnsLookupFailed?, .dataNotAllowed?:
                throw LioMenuFailure.offline
            default: throw error is LioMenuFailure ? error : LioMenuFailure.unavailable
            }
        }
        try requireCurrentSession()
        guard let http = response as? HTTPURLResponse, http.url == url else { throw LioMenuFailure.unavailable }
        guard http.statusCode == 200 else { throw LioMenuWire.failure(status: http.statusCode) }
        return try LioMenuWire.read(data)
    }

    private func requireCurrentSession() throws {
        guard isCurrent() else { throw CancellationError() }
        try Task.checkCancellation()
    }
}

extension LioMenuService {
    @MainActor static func relay(_ client: LioMenuRelayClient) -> LioMenuService {
        LioMenuService { jpeg in try await client.read(jpeg) }
    }
}

#if os(iOS)
extension LioMenuRelayClient {
    /// Internal testers only, when the build enables menu ordering (`G2CMenuOrderEnabled`, off by default);
    /// the relay decides per account.
    public static func internalBeta(endpoint: MessageEndpoint, isCurrent: @escaping @MainActor () -> Bool,
                                    bearer: @escaping @MainActor () -> String?) -> LioMenuRelayClient? {
        guard endpoint.allowsDemoBetaActivation,
              Bundle.main.object(forInfoDictionaryKey: "G2CMenuOrderEnabled") as? String == "YES" else { return nil }
        return LioMenuRelayClient(baseURL: endpoint.url, isCurrent: isCurrent, bearer: bearer) { request in
            let policy = URLSessionConfiguration.ephemeral
            policy.timeoutIntervalForResource = LioMenuWire.timeout
            policy.urlCache = nil
            policy.httpCookieStorage = nil
            policy.urlCredentialStorage = nil
            let delegate = LioRelayNoRedirect(bodyLength: request.httpBody?.count ?? 0, uploadFinished: nil)
            let session = URLSession(configuration: policy, delegate: delegate, delegateQueue: nil)
            defer { session.invalidateAndCancel() }
            let (stream, response) = try await session.bytes(for: request)
            let limit = min(endpoint.maximumResponseBytes, LioMenuWire.maximumReply)
            guard response.expectedContentLength <= limit else { throw LioMenuFailure.unavailable }
            var body = Data()
            for try await byte in stream {
                guard body.count < limit else { throw LioMenuFailure.unavailable }
                body.append(byte)
            }
            return (body, response)
        }
    }
}
#endif
