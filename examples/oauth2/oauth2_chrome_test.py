import os

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def test_chrome():
    browser = "CHROME"
    driver = webdriver.Remote(
      command_executor='http://selenium-grid-selenium-hub:4444/wd/hub',
      desired_capabilities=getattr(DesiredCapabilities, browser)
    )
    driver.get("http://kube-selenium.default.svc.cluster.local:8000/db/migrate")
    driver.get("http://kube-selenium.default.svc.cluster.local:8000/session/new")
    testdata = {
        'oauth2_client_id': os.environ['OAUTH2_CLIENT_ID'],
        'oauth2_client_secret': os.environ['OAUTH2_CLIENT_SECRET'],
        'oauth2_authz_endpoint_url': os.environ['OAUTH2_AUTHZ_ENDPOINT_URL'],
        'oauth2_token_endpoint_url': os.environ['OAUTH2_TOKEN_ENDPOINT_URL'],
        'scopes': os.environ['OAUTH2_SCOPES'],
        'http_request_method': os.getenv('HTTP_REQUEST_METHOD', 'GET'),
        'http_request_url': os.environ['HTTP_REQUEST_URL'],
    }
    for k in testdata:
        v = testdata[k]
        input = driver.find_element_by_id(k)
        input.send_keys(v)

    form = driver.find_element_by_css_selector("form")
    form.submit()

    assert "mumoshu" in driver.page_source
    driver.close()
    print("Browser %s checks out!" % browser)
