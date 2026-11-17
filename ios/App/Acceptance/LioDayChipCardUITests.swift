import XCTest
@MainActor final class LioDayChipCardUITests:XCTestCase {
 func testEnglishDefaultAndDaySwitching() throws { try exercise(chinese:false,dark:false,largest:false) }
 func testChineseDefaultAndDaySwitching() throws { try exercise(chinese:true,dark:false,largest:false) }
 func testEnglishDarkDefaultCard() throws { try exercise(chinese:false,dark:true,largest:false) }
 func testChineseDarkDefaultCard() throws { try exercise(chinese:true,dark:true,largest:false) }
 func testEnglishLargestDarkCard() throws { try exercise(chinese:false,dark:true,largest:true) }
 func testChineseLargestDarkCard() throws { try exercise(chinese:true,dark:true,largest:true) }
 private func exercise(chinese:Bool,dark:Bool,largest:Bool)throws {
  continueAfterFailure=false
  let app=XCUIApplication(bundleIdentifier:"space.go2china.card.acceptance")
  app.launchArguments=["--lio-preview","-cj.ui.language.v1",chinese ? "zh-Hans":"en","-lio.ui.appearance.v1",dark ? "dark":"light","-UIPreferredContentSizeCategoryName",largest ? "UICTContentSizeCategoryAccessibilityXXXL":"UICTContentSizeCategoryL"]
  app.launch();defer { app.terminate() }
  let first=app.buttons["lio.trip.day.1"]
  XCTAssertTrue(first.waitForExistence(timeout:10))
  XCTAssertTrue(first.isSelected)
  XCTAssertTrue(app.staticTexts["Day1 stop 1"].exists)
  XCTAssertTrue(app.staticTexts["Day1 stop 4"].exists)
  XCTAssertFalse(app.staticTexts["Day1 stop 5"].exists)
  XCTAssertFalse(app.staticTexts["Day2 stop"].exists)
  XCTAssertEqual(app.staticTexts["lio.trip.more-stops"].label,chinese ? "还有 2 项安排":"2 more stops")
  XCTAssertTrue(app.staticTexts[chinese ? "出发日期待定":"Start date not set"].exists)
  let initial=XCTAttachment(screenshot:app.screenshot());initial.name="initial-day-card-\(chinese ? "zh":"en")-\(dark ? "dark":"light")-\(largest ? "largest":"normal")";initial.lifetime = .keepAlways;add(initial)
  try app.performAccessibilityAudit(for:.all)
  let second=app.buttons["lio.trip.day.2"]
  if !second.isHittable { app.swipeUp() }
  second.tap()
  XCTAssertTrue(second.isSelected)
  XCTAssertFalse(app.staticTexts["Day1 stop 1"].exists)
  XCTAssertTrue(app.staticTexts["Day2 stop"].exists)
  XCTAssertFalse(app.staticTexts["lio.trip.more-stops"].exists)
  let third=app.buttons["lio.trip.day.3"]
  if !third.isHittable { app.swipeUp() }
  third.tap()
  XCTAssertTrue(app.staticTexts["lio.trip.day.empty"].exists)
  let show=app.buttons["lio.trip.show"]
  if !show.isHittable { app.swipeUp() }
  XCTAssertGreaterThanOrEqual(show.frame.height,44)
  show.tap()
  XCTAssertEqual(app.staticTexts["fixture.card.viewed"].label,"1")
  try app.performAccessibilityAudit(for:.all)
  let image=XCTAttachment(screenshot:app.screenshot());image.name="card-\(chinese ? "zh":"en")-\(dark ? "dark":"light")";image.lifetime = .keepAlways;add(image)
 }
}
