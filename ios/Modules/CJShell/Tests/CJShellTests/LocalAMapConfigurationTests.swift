#if DEBUG
import Foundation
import Testing
@testable import CJShell

struct LocalAMapConfigurationTests {
    @Test func onlyTheBoundBundleAndValidLocalResourceCanProvideAKey() throws {
        let data = try PropertyListSerialization.data(fromPropertyList:["apiKey":"SYNTHETIC-LOCAL-KEY"],format:.binary,options:0)
        #expect(LocalAMapConfiguration.key(data:data,bundleID:"space.go2china.app") == "SYNTHETIC-LOCAL-KEY")
        for id in [nil,"space.go2china.foundation.local","space.go2china.scoped.acceptance"] {
            #expect(LocalAMapConfiguration.key(data:data,bundleID:id) == nil)
        }
        let invalidValues: [[String:Any]] = [["apiKey":""],["apiKey":"line\nbreak"],["apiKey":7],["apiKey":"synthetic","other":"unexpected"],[:]]
        for value in invalidValues {
            let invalid = try PropertyListSerialization.data(fromPropertyList:value,format:.binary,options:0)
            #expect(LocalAMapConfiguration.key(data:invalid,bundleID:"space.go2china.app") == nil)
        }
        #expect(LocalAMapConfiguration.key(data:Data("not a plist".utf8),bundleID:"space.go2china.app") == nil)
    }
}
#endif
