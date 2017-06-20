from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def test_chrome():
    browser = "CHROME"
    driver = webdriver.Remote(
      command_executor='http://selenium-grid-selenium-hub:4444/wd/hub',
      desired_capabilities=getattr(DesiredCapabilities, browser)
    )
    driver.get("http://google.com")
    assert "google" in driver.page_source
    driver.close()
    print("Browser %s checks out!" % browser)
