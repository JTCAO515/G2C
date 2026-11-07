import XCTest
import Foundation

#if G2C_M4_DEVICE_ACCEPTANCE
/// This uses the real Settings controls while XCTest stays connected over USB.
@MainActor private final class OfflineRadioSettings {
    private enum Failure: Error { case unavailableControl, invalidValue, unexpectedInitialState, unverifiedChange }
    private struct Original {
        let bluetooth: String
        var wifiInAirplane: String?
    }

    private let settings = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
    private let wifiLabels = ["无线局域网", "Wi-Fi", "Wi‑Fi"]
    private let bluetoothLabels = ["蓝牙", "Bluetooth"]
    private var original: Original?
    var needsRestore: Bool { original != nil }

    func disconnect() throws {
        settings.launch()
        guard try value(airplane()) == "0", try value(wifi()) == "1" else {
            throw Failure.unexpectedInitialState
        }
        original = Original(bluetooth: try value(bluetooth()))
        print("M4_PHYSICAL_RADIO_RESTORE_PENDING")
        try set("1", on: airplane())
        let wlan = try wifi()
        original?.wifiInAirplane = try value(wlan)
        try set("0", on: wlan)
        print("M4_PHYSICAL_RADIOS_OFFLINE airplane=1 wifi=0")
    }

    func requireDisconnected() throws {
        settings.activate()
        guard try value(airplane()) == "1", try value(wifi()) == "0" else {
            throw Failure.unverifiedChange
        }
        print("M4_PHYSICAL_RADIOS_AFTER_REOPEN airplane=1 wifi=0")
    }

    func restore() throws {
        guard let original else { return }
        settings.activate()
        // Preserve the remembered Wi-Fi choice while in airplane mode as well
        // as the visible switches when returning to the original network.
        if let remembered = original.wifiInAirplane, try value(airplane()) == "1" {
            try set(remembered, on: wifi())
        }
        try set("0", on: airplane())
        try set("1", on: wifi())
        try set(original.bluetooth, on: bluetooth())
        self.original = nil
        settings.terminate()
        print("M4_PHYSICAL_RADIOS_RESTORED airplane=0 wifi=1 bluetooth=\(original.bluetooth)")
    }

    private func airplane() throws -> XCUIElement {
        guard settings.wait(for: .runningForeground, timeout: 15) else { throw Failure.unavailableControl }
        let control = settings.switches.matching(NSPredicate(format: "label IN %@ OR identifier IN %@",
            ["飞行模式", "Airplane Mode"], ["AIRPLANE_MODE", "Airplane Mode"]))
        for _ in 0..<6 {
            if control.count == 1 { return try visible(control) }
            let back = settings.navigationBars.buttons.matching(NSPredicate(format: "label IN %@",
                ["设置", "Settings", "返回", "Back", "通用", "General", "辅助功能", "Accessibility",
                 "显示与亮度", "Display & Brightness", "显示与文字大小", "Display & Text Size"]))
            try visible(back).tap()
        }
        throw Failure.unavailableControl
    }

    private func wifi() throws -> XCUIElement { try detailSwitch(labels: wifiLabels, identifier: "WIFI") }
    private func bluetooth() throws -> XCUIElement { try detailSwitch(labels: bluetoothLabels, identifier: "BLUETOOTH") }

    private func detailSwitch(labels: [String], identifier: String) throws -> XCUIElement {
        _ = try airplane()
        let row = settings.staticTexts.matching(NSPredicate(format: "label IN %@", labels))
        try visible(row).tap()
        return try visible(settings.switches.matching(NSPredicate(format: "label IN %@ OR identifier IN %@",
            labels, [identifier] + labels)))
    }

    private func visible(_ query: XCUIElementQuery) throws -> XCUIElement {
        guard query.firstMatch.waitForExistence(timeout: 8), query.count == 1,
              query.element.isHittable else { throw Failure.unavailableControl }
        return query.element
    }

    private func value(_ control: XCUIElement) throws -> String {
        guard let value = control.value as? String, value == "0" || value == "1" else { throw Failure.invalidValue }
        return value
    }

    private func set(_ expected: String, on control: XCUIElement) throws {
        guard try value(control) != expected else { return }
        guard control.isEnabled else { throw Failure.unavailableControl }
        // iOS Settings may expose the whole row as the switch. For that
        // layout, target the trailing control within the exact matched row.
        let width = control.frame.width
        if width > 110 {
            control.coordinate(withNormalizedOffset: CGVector(dx: (width - 42) / width, dy: 0.5)).tap()
        } else {
            control.tap()
        }
        let settled = XCTNSPredicateExpectation(predicate: NSPredicate { object, _ in
            (object as? XCUIElement)?.value as? String == expected
        }, object: control)
        guard XCTWaiter.wait(for: [settled], timeout: 10) == .completed else { throw Failure.unverifiedChange }
    }
}
#endif

@MainActor final class DevelopmentOfflineTripUITests: XCTestCase {
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    #if G2C_M4_DEVICE_ACCEPTANCE
    private lazy var deviceSession = M4DeviceTestSession(test: self, control: control)
    #endif
    struct Fixture: Decodable {
        let endpoint: String
        let accounts: [String: String]
        let subjects: [String: String]
        let case_id: String
        let physical_radio_offline: Bool?
    }
    struct Record: Decodable { let trip_id: String; let version: Int; let title: String; let sha256: String }
    struct Snapshot { let hash: String; let synced: String; let deadline: String }

    @discardableResult func call(_ path: String, _ fixture: Fixture, _ values: [String: String] = [:]) async throws -> Data {
        var url = try XCTUnwrap(URLComponents(string: control + path))
        url.queryItems = values.merging(["case": fixture.case_id]) { _, new in new }.map { URLQueryItem(name: $0.key, value: $0.value) }
        #if G2C_M4_DEVICE_ACCEPTANCE
        let (data, response) = try await deviceSession.data(from: XCTUnwrap(url.url))
        #else
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        #endif
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200, path)
        return data
    }
    func prepare(_ name: String) async throws -> (Fixture, Record) {
        var url = try XCTUnwrap(URLComponents(string: control + "/prepare"))
        url.queryItems = [.init(name: "case", value: name)]
        #if G2C_M4_DEVICE_ACCEPTANCE
        let (data, response) = try await deviceSession.data(from: XCTUnwrap(url.url))
        #else
        let (data, response) = try await URLSession.shared.data(from: XCTUnwrap(url.url))
        #endif
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        let fixture = try JSONDecoder().decode(Fixture.self, from: data)
        let records = try JSONDecoder().decode([Record].self, from: await call("/create", fixture))
        XCTAssertEqual(records.count, 1)
        XCTAssertTrue(records[0].title.contains("北京"))
        return (fixture, records[0])
    }
    func tap(_ id: String) {
        let fixed=["Memory","记忆","Trips","行程","Assistant","助手"].contains(id)
        let query = fixed ? app.tabBars.buttons.matching(identifier: id) : app.buttons.matching(identifier: id)
        let target = query.element
        #if G2C_M4_DEVICE_ACCEPTANCE
        if fixed {XCTAssertTrue(target.waitForExistence(timeout:10),id)}
        else {deviceSession.revealControl(target,in:app,diagnosticIdentifier:id)}
        #else
        for _ in 0..<35 {
            if target.exists && target.isHittable { break }
            if target.exists && target.frame.midY < app.navigationBars.element.frame.maxY { app.swipeDown() }
            else { app.swipeUp() }
        }
        #endif
        XCTAssertEqual(query.count, 1, id)
        XCTAssertTrue(target.isHittable, id)
        let enabled = XCTNSPredicateExpectation(predicate: NSPredicate(format: "enabled == true"), object: target)
        XCTAssertEqual(XCTWaiter.wait(for: [enabled], timeout: 20), .completed, id)
        #if G2C_M4_DEVICE_ACCEPTANCE
        if id == "offline.sync" {
            print("M4_OFFLINE_SYNC_TARGET",target.frame)
            let shot=XCTAttachment(screenshot:app.screenshot());shot.name="offline-sync-before-touch";shot.lifetime = .keepAlways;add(shot)
        }
        target.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
        #else
        target.tap()
        #endif
        #if G2C_M4_DEVICE_ACCEPTANCE
        if fixed {
            let selected=XCTNSPredicateExpectation(predicate:NSPredicate(format:"selected == true"),object:target)
            XCTAssertEqual(XCTWaiter.wait(for:[selected],timeout:10),.completed,id)
        }
        if id.hasPrefix("account.development.signin.") || id == "account.development.restore" {
            deviceSession.waitForAppNetworkConsent()
        }
        #endif
    }
    func launch(_ f: Fixture, language: String = "en", offsets: [String: String] = [:], choices: Bool = true) async throws {
        continueAfterFailure = false
        app?.terminate(); app = XCUIApplication(bundleIdentifier: "space.go2china.offline-trip.acceptance")
        app.launchArguments = ["-cj.ui.language.v1", language]
        #if G2C_M4_DEVICE_ACCEPTANCE
        let accountsJSON = "{}"
        if choices { try await deviceSession.stageAccounts(caseID: f.case_id) }
        #else
        let accountsJSON = choices ? String(data: try JSONEncoder().encode(f.accounts), encoding: .utf8)! : "{}"
        #endif
        app.launchEnvironment = ["OS_ACTIVITY_MODE": "disable", "G2C_DEV_ACCOUNT_MODE": "1",
            "G2C_DEV_API_BASE_URL": f.endpoint, "G2C_DEV_OFFLINE_TRIP": "last-sync-v1",
            "G2C_DEV_ACCOUNTS": accountsJSON]
            .merging(offsets) { _, new in new }
        #if G2C_M4_DEVICE_ACCEPTANCE
        app.launchEnvironment.merge(try deviceSession.applicationEnvironment(endpoint: f.endpoint, injecting: choices)) { _, value in value }
        let diagnostic=UUID().uuidString
        app.launchEnvironment["G2C_M4_DIAGNOSTIC_ID"]=diagnostic
        print("M4_OFFLINE_DIAGNOSTIC_ID",diagnostic)
        #endif
        app.launch()
        XCTAssertTrue(app.tabBars.element.waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts["g2c.dev.error"].exists)
    }
    func account(_ language: String = "en") {
        tap(language == "en" ? "Memory" : "记忆")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
    }
    func signed(_ f: Fixture, as key: String = "A") {
        #if G2C_M4_DEVICE_ACCEPTANCE
        deviceSession.requireAccount(f.subjects[key]!,in:app)
        #endif
        let value = app.staticTexts["account.development.status"]
        let expected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", f.subjects[key]!), object: value)
        XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 20), .completed)
    }
    func initialLogin(_ f: Fixture) {
        account(); tap("account.development.signin.A"); signed(f)
    }
    func synchronize(_ record: Record) {
        tap("Trips"); tap("trips.refresh")
        let row = app.buttons["trips.item." + record.trip_id]
        XCTAssertTrue(row.waitForExistence(timeout: 20)); tap("trips.item." + record.trip_id)
        tap("offline.sync")
        let status = app.staticTexts["offline.sync.status"]
        let saved = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@",
            "Offline snapshot saved from this successful formal-trip read."), object: status)
        let result=XCTWaiter.wait(for:[saved],timeout:25)
        if result != .completed {
            let shot=XCTAttachment(screenshot:app.screenshot());shot.name="offline-sync-unconfirmed";shot.lifetime = .keepAlways;add(shot)
            let tree=XCTAttachment(string:app.debugDescription);tree.name="offline-sync-unconfirmed-tree";tree.lifetime = .keepAlways;add(tree)
        }
        XCTAssertEqual(result,.completed,status.label)
        app.navigationBars.buttons.element(boundBy: 0).tap()
    }
    @discardableResult func openCache(_ record: Record, language: String = "en") -> Snapshot {
        tap(language == "en" ? "Trips" : "行程")
        if !app.staticTexts["offline.notice"].exists { tap("offline.open") }
        let title = app.staticTexts["offline.title"]
        XCTAssertTrue(title.waitForExistence(timeout: 15), app.staticTexts["offline.state"].label)
        XCTAssertEqual(title.label, record.title)
        XCTAssertEqual(app.staticTexts["offline.tripID"].label, record.trip_id)
        let hash = app.staticTexts["offline.hash"].label
        XCTAssertEqual(hash.count, 64)
        let item = app.staticTexts.matching(NSPredicate(format: "identifier BEGINSWITH %@", "offline.item.")).allElementsBoundByIndex
        XCTAssertFalse(item.isEmpty)
        XCTAssertTrue(item.contains(where: { $0.label.contains("故宫") || $0.label.contains("天坛") }))
        return .init(hash: hash, synced: app.staticTexts["offline.syncedAt"].label, deadline: app.staticTexts["offline.deadline"].label)
    }
    func expectDenied(_ fragment: String) {
        tap("Trips"); tap("offline.open")
        let value = app.staticTexts["offline.state"]
        XCTAssertTrue(value.waitForExistence(timeout: 15))
        let expected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", fragment), object: value)
        XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 15), .completed, value.label)
        XCTAssertFalse(app.staticTexts["offline.title"].exists)
        XCTAssertFalse(app.staticTexts["offline.hash"].exists)
    }
    func audit(_ name: String) throws {
        let ids = app.staticTexts["offline.title"].exists
            ? ["offline.notice", "offline.tripID", "offline.hash", "offline.title", "offline.read"]
            : ["offline.notice", "offline.state", "offline.read"]
        for id in ids {
            let target = id == "offline.read" ? app.buttons[id] : app.staticTexts[id]
            for _ in 0..<35 {
                let top = app.navigationBars.element.frame.maxY, bottom = app.tabBars.element.frame.minY
                if target.exists && target.isHittable && target.frame.midY > top && target.frame.midY < bottom { break }
                if target.exists && target.frame.midY < top { app.swipeDown() } else { app.swipeUp() }
            }
            XCTAssertTrue(target.isHittable, id)
            continueAfterFailure = true
            var issues = 0
            try app.performAccessibilityAudit(for: .all) { issue in
                issues += 1; print(name, id, issue.detailedDescription, issue.element?.label ?? "unavailable"); return false
            }
            continueAfterFailure = false; XCTAssertEqual(issues, 0)
            let image = XCTAttachment(screenshot: app.screenshot())
            image.name = name + "-" + id; image.lifetime = .keepAlways; add(image)
        }
    }

    #if G2C_M4_DEVICE_ACCEPTANCE
    func testClockBootstrapDiagnostic() async throws {
        let (f, _) = try await prepare("testReopenLanguageAndReadOnly")
        defer {app?.terminate()}
        try await launch(f);initialLogin(f)
        // The real App constructor has opened the protected marker and the
        // entitled kernel object. No synchronization/read acceptance is claimed.
        XCTAssertFalse(app.staticTexts["g2c.dev.error"].exists)
        tap("Trips")
        let tree=XCTAttachment(string:app.debugDescription);tree.name="offline-entry-before-reveal";tree.lifetime = .keepAlways;add(tree)
        tap("offline.open")
        XCTAssertTrue(app.buttons.matching(identifier:"offline.read").element.waitForExistence(timeout:10))
    }
    #endif
    func testReopenLanguageAndReadOnly() async throws {
        let (f, record) = try await prepare("testReopenLanguageAndReadOnly")
        defer { app?.terminate() }
        #if G2C_M4_DEVICE_ACCEPTANCE
        let radios = f.physical_radio_offline == true ? OfflineRadioSettings() : nil
        defer {
            if let radios, radios.needsRestore {
                do { try radios.restore() }
                catch { XCTFail("Could not verify restoration of the original radio settings") }
            }
        }
        #endif
        try await launch(f); initialLogin(f); synchronize(record)
        let original = openCache(record)
        try await call("/verify", f, ["stage": "checkpoint", "snapshot_hash": original.hash])
        try await call("/checkpoint", f)
        tap("offline.read")
        try audit("offline-en-standard")
        try await call("/verify", f, ["network": "none", "stage": "unchanged", "snapshot_hash": original.hash])
        try await call("/offline", f)
        #if G2C_M4_DEVICE_ACCEPTANCE
        if let radios { try radios.disconnect() }
        #endif
        try await launch(f, choices: false)
        let reopened = openCache(record)
        XCTAssertEqual(reopened.hash, original.hash); XCTAssertEqual(reopened.deadline, original.deadline)
        account(); app.navigationBars.buttons.element(boundBy: 0).tap()
        tap("memory.language"); tap("简体中文")
        let chinese = openCache(record, language: "zh-Hans")
        XCTAssertEqual(chinese.hash, original.hash)
        XCTAssertEqual(chinese.deadline.components(separatedBy: "：").last, original.deadline.components(separatedBy: ": ").last)
        try audit("offline-zh-default")
        #if G2C_M4_DEVICE_ACCEPTANCE
        if let radios {
            try radios.requireDisconnected()
            try radios.restore()
            app.activate()
            XCTAssertTrue(app.wait(for: .runningForeground, timeout: 15))
        }
        #endif
        try await call("/verify", f, ["network": "none", "stage": "unchanged", "snapshot_hash": original.hash])
        try await call("/online", f)
    }
    func testExpiryRollbackAndUntrustedTime() async throws {
        let (f, record) = try await prepare("testExpiryRollbackAndUntrustedTime")
        defer { app?.terminate() }
        try await launch(f); initialLogin(f); synchronize(record)
        let original = openCache(record)
        try await call("/verify", f, ["stage": "checkpoint", "snapshot_hash": original.hash])
        try await call("/offline", f)
        try await launch(f, offsets: ["G2C_DEV_OFFLINE_WALL_OFFSET": "1209600", "G2C_DEV_OFFLINE_UPTIME_OFFSET": "1209600"], choices: false)
        expectDenied("has expired"); try audit("offline-expired")
        try await call("/verify", f, ["stage": "unchanged"])
        try await launch(f, offsets: ["G2C_DEV_OFFLINE_WALL_OFFSET": "-3600"], choices: false)
        expectDenied("cannot be trusted"); try await call("/verify", f, ["stage": "unchanged"])
        try await launch(f, offsets: ["G2C_DEV_OFFLINE_TIME_TRUSTED": "0"], choices: false)
        expectDenied("cannot be trusted"); try await call("/verify", f, ["stage": "unchanged"])
        try await call("/online", f)
        try await launch(f); account(); tap("account.development.restore"); signed(f)
        synchronize(record)
        let renewed = openCache(record)
        XCTAssertNotEqual(renewed.synced, original.synced)
        XCTAssertNotEqual(renewed.deadline, original.deadline)
        try await call("/verify", f, ["snapshot_hash": renewed.hash])
    }
    func testAccountSwitchAndLogout() async throws {
        let (f, record) = try await prepare("testAccountSwitchAndLogout")
        defer { app?.terminate() }
        try await launch(f); initialLogin(f); synchronize(record); _ = openCache(record)
        account(); tap("account.development.signin.B"); signed(f, as: "B")
        tap("Trips"); tap("offline.open")
        XCTAssertFalse(app.staticTexts["offline.title"].exists)
        try await call("/verify", f, ["files": "0"])
        account(); tap("account.development.signin.A"); signed(f)
        synchronize(record); _ = openCache(record)
        account(); tap("account.development.signout")
        try await call("/verify", f, ["files": "0"])
        try await launch(f, choices: false); expectDenied("No offline snapshot")
        try audit("offline-after-logout")
        try await call("/verify", f, ["files": "0"])
    }
    func testTemporaryFailuresAndIdentityDenial() async throws {
        let (f, record) = try await prepare("testTemporaryFailuresAndIdentityDenial")
        defer { app?.terminate() }
        try await launch(f); initialLogin(f); synchronize(record)
        let original = openCache(record)
        try await call("/verify", f, ["stage": "checkpoint", "snapshot_hash": original.hash])
        for mode in ["503", "unknown", "network"] {
            if mode == "network" { try await call("/offline", f) }
            else { try await call("/mode", f, ["value": mode]) }
            account(); tap("account.development.restore")
            let status = app.staticTexts["account.development.status"]
            let unknown = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", "Cannot verify the session"), object: status)
            XCTAssertEqual(XCTWaiter.wait(for: [unknown], timeout: 25), .completed)
            let retained = openCache(record)
            XCTAssertEqual(retained.hash, original.hash); XCTAssertEqual(retained.deadline, original.deadline)
            try await call("/verify", f, ["stage": "unchanged", "snapshot_hash": original.hash])
            if mode == "network" { try await call("/online", f) }
        }
        try await call("/revoke", f)
        account(); tap("account.development.restore")
        let rejected = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", "Sign-in was rejected"), object: app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for: [rejected], timeout: 25), .completed)
        tap("Trips")
        if !app.staticTexts["offline.notice"].exists { tap("offline.open") }
        XCTAssertFalse(app.staticTexts["offline.title"].exists)
        try await call("/verify", f, ["stage": "denied", "files": "0"])
        try await launch(f, choices: false); expectDenied("No offline snapshot")
        try await call("/verify", f, ["stage": "denied", "files": "0"])
    }
}
