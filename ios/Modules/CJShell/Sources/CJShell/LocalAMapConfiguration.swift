#if DEBUG
import Foundation

/// Local resource boundary only; never returns file contents in an error/log.
enum LocalAMapConfiguration {
    static func key(data: Data, bundleID: String?) -> String? {
        guard bundleID == "space.go2china.app" else { return nil }
        do {
            let value = try PropertyListSerialization.propertyList(from: data, format: nil)
            guard let fields = value as? [String:String], Set(fields.keys) == ["apiKey"],
                  let key = fields["apiKey"], !key.isEmpty,
                  key.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) }) else { return nil }
            return key
        } catch {
            return nil
        }
    }
}
#endif
