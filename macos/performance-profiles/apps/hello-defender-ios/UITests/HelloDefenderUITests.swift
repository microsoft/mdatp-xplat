import XCTest

final class HelloDefenderUITests: XCTestCase {
    func testHelloTitleIsVisible() {
        let app = XCUIApplication()
        app.launch()

        XCTAssertTrue(app.staticTexts["helloTitle"].waitForExistence(timeout: 5))
    }
}
