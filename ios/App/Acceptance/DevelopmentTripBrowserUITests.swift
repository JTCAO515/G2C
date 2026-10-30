import XCTest
import Foundation

@MainActor final class DevelopmentTripBrowserUITests: XCTestCase {
    let control = "__FIXTURE_URL__"
    var app: XCUIApplication!
    struct Fixture: Decodable { let endpoint: String; let accounts: [String:String]; let subjects: [String:String]; let case_id: String }
    struct Record: Decodable { let trip_id: String; let version: Int; let title: String; let sha256: String }
    func call(_ path: String, _ values: [String:String]) async throws -> Data {
        var url=URLComponents(string:control+path)!;url.queryItems=values.map { URLQueryItem(name:$0.key,value:$0.value) }
        let (data,response)=try await URLSession.shared.data(from:XCTUnwrap(url.url))
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode,200);return data
    }
    func tap(_ id: String) {
        let target=app.buttons.matching(identifier:id).firstMatch
        for _ in 0..<80 {
            if target.isHittable { break }
            if target.exists && target.frame.maxY < app.navigationBars.firstMatch.frame.maxY { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(target.waitForExistence(timeout:10),id)
        XCTAssertTrue(target.isHittable,id)
        let enabled=XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:target)
        XCTAssertEqual(XCTWaiter.wait(for:[enabled],timeout:15),.completed,id)
        target.tap()
    }
    func launch(_ f: Fixture, language: String, large: Bool = false) throws {
        app?.terminate();app=XCUIApplication(bundleIdentifier:"space.go2china.trip-browser.acceptance")
        app.launchArguments=["-cj.ui.language.v1",language]
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName","UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment=["G2C_DEV_ACCOUNT_MODE":"1","G2C_DEV_API_BASE_URL":f.endpoint,
            "G2C_DEV_ACCOUNTS":String(data:try JSONEncoder().encode(f.accounts),encoding:.utf8)!]
        app.launch();tap(language=="en" ? "Memory":"记忆");tap("memory.account")
        tap("account.development.signout");tap("account.development.signin.A")
        let signed=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",f.subjects["A"]!),object:app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[signed],timeout:20),.completed)
        tap(language=="en" ? "Trips":"行程")
    }
    func capture(_ name: String) { let a=XCTAttachment(screenshot:app.screenshot());a.name=name;a.lifetime = .keepAlways;add(a) }
    func audit(_ name: String) throws {
        var count=0;continueAfterFailure=true;defer { continueAfterFailure=false }
        try app.performAccessibilityAudit(for:.all) { issue in count += 1;print(name,issue.detailedDescription,issue.element?.label ?? "unavailable");return false }
        continueAfterFailure=false;XCTAssertEqual(count,0)
    }
    func open(_ record: Record, language: String, towardsEnd: Bool = false) {
        let row=app.buttons["trips.item."+record.trip_id]
        let top=app.navigationBars.firstMatch.frame.maxY,bottom=app.tabBars.firstMatch.frame.minY
        for _ in 0..<80 {
            if row.isHittable && row.frame.midY>top && row.frame.midY<bottom { break }
            if !row.exists { if towardsEnd { app.swipeUp() } else { app.swipeDown() } }
            else if row.frame.midY<=top { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(row.waitForExistence(timeout:10));XCTAssertTrue(row.isHittable);XCTAssertGreaterThan(row.frame.midY,top);XCTAssertLessThan(row.frame.midY,bottom)
        row.coordinate(withNormalizedOffset:CGVector(dx:0.5,dy:0.5)).tap()
        XCTAssertFalse(app.staticTexts["trip.detail.id"].exists)
        tap("trips.detail.read")
        let id=app.staticTexts["trip.detail.id"]
        XCTAssertTrue(id.waitForExistence(timeout:15));XCTAssertEqual(id.label,record.trip_id)
        XCTAssertEqual(app.staticTexts["trip.detail.version"].label,language=="en" ? "Current formal version \(record.version)":"当前正式版本 \(record.version)")
        XCTAssertTrue(app.staticTexts[record.title].exists)
    }
    func browse(_ language: String, large: Bool) async throws {
        continueAfterFailure=false
        let name=large ? "testChineseLarge":"testEnglish"
        let f=try JSONDecoder().decode(Fixture.self,from:await call("/prepare",["case":name]))
        defer { app?.terminate() };try launch(f,language:language,large:large)
        tap("trips.refresh")
        XCTAssertTrue(app.staticTexts[language=="en" ? "No trips returned":"暂无行程"].waitForExistence(timeout:15))
        capture("empty-"+language)
        let records=try JSONDecoder().decode([Record].self,from:await call("/create",["case":f.case_id]))
        XCTAssertEqual(records.count,21)
        tap("trips.refresh");XCTAssertTrue(app.buttons["trips.item."+records[0].trip_id].waitForExistence(timeout:15))
        XCTAssertFalse(app.staticTexts["trip.detail.id"].exists)
        XCTAssertFalse(app.buttons["trips.item."+records[20].trip_id].exists)
        tap("trips.next")
        XCTAssertTrue(app.buttons["trips.item."+records[20].trip_id].waitForExistence(timeout:15))
        for (index,record) in [records[20],records[0],records[20]].enumerated() {
            open(record,language:language,towardsEnd:record.trip_id==records[20].trip_id);capture("explicit-selection-"+String(index)+"-"+language)
            try audit("TRIP_DETAIL_"+language);app.navigationBars.buttons.firstMatch.tap()
        }
        tap(language=="en" ? "Memory":"记忆")
        if app.staticTexts["account.development.status"].exists { app.navigationBars.buttons.firstMatch.tap() }
        tap("memory.language");tap(language=="en" ? "简体中文":"English");app.navigationBars.buttons.firstMatch.tap()
        let switched=language=="en" ? "zh-Hans":"en"
        tap(switched=="en" ? "Trips":"行程")
        open(records[0],language:switched);capture("same-formal-record-after-language-change")
        _ = try await call("/verify",["case":f.case_id,"stage":"browse"])
    }
    func testEnglish() async throws { try await browse("en",large:false) }
    func testChineseLarge() async throws { try await browse("zh-Hans",large:true) }
    func testAccountLateRead() async throws {
        continueAfterFailure=false
        let f=try JSONDecoder().decode(Fixture.self,from:await call("/prepare",["case":"testAccountLateRead"]))
        defer { app?.terminate() };try launch(f,language:"en")
        let records=try JSONDecoder().decode([Record].self,from:await call("/create",["case":f.case_id]))
        tap("trips.refresh");open(records[0],language:"en")
        _ = try await call("/hold",["case":f.case_id,"trip_id":records[0].trip_id])
        tap("trips.detail.read");_ = try await call("/wait-held",["case":f.case_id])
        tap("Memory")
        if !app.staticTexts["account.development.status"].exists { tap("memory.account") }
        tap("account.development.signin.B")
        let signed=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@",f.subjects["B"]!),object:app.staticTexts["account.development.status"])
        XCTAssertEqual(XCTWaiter.wait(for:[signed],timeout:20),.completed)
        _ = try await call("/release",["case":f.case_id])
        tap("Trips");XCTAssertFalse(app.staticTexts["trip.detail.id"].exists)
        tap("trips.refresh");XCTAssertTrue(app.staticTexts["No trips returned"].waitForExistence(timeout:15))
        XCTAssertFalse(app.buttons["trips.item."+records[0].trip_id].exists)
        capture("B-has-no-A-formal-records");_ = try await call("/verify",["case":f.case_id,"stage":"late"])
    }
}
