"""
Browser session management for law document crawler.
Features:
- Automated Google login handling
- Cookie management and persistence
- Session validation and renewal
- Browser automation with selenium-stealth
- Error detection and recovery
- Page status verification
"""

import os
import time
import pickle
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from utils.common import setup_logger, capture_page_source, retry_fetch_url
from utils.document_formatter import format_document_name
from utils.logger_setup import ErrorLogger


class LawVNSession:
    BASE_URL = "https://luatvietnam.vn"

    def __init__(self, debug=False, headless=True):
        self.debug = debug
        self.headless = headless
        self.logger = setup_logger(debug)
        self.config = self._load_config()
        self.driver = None
        self.setup_driver()
        self.ERROR_MARKERS = {
            "404": [
                "cat-box-404",
                "Không tìm thấy trang",
                "URL không tồn tại",
                "/404.html",
            ],
            "login_required": [
                "lawsVnLogin",
                "Quý khách vui lòng đăng nhập",
                "tooltip-text-2",
                'class="btn-login"',
            ],
        }
        self.error_logger = ErrorLogger()

        # Add page load timeout settings
        self.page_load_timeout = 15  # Default 15 seconds
        self.polling_interval = 0.5  # Check every 0.5 seconds
        self.min_wait = 1  # Minimum wait after page appears loaded

    def setup_driver(self):
        """Initialize browser session with selenium-stealth"""
        try:
            options = Options()

            # Setup download directory
            download_dir = os.path.abspath("downloads")
            if not os.path.exists(download_dir):
                os.makedirs(download_dir)

            prefs = {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "plugins.always_open_pdf_externally": True,
                "profile.default_content_settings.popups": 0,
                "profile.content_settings.exceptions.automatic_downloads.*.setting": 1,
            }

            # Improved headless mode configuration
            if self.headless:
                options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-software-rasterizer")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                # Set a larger window size for headless mode
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--start-maximized")
                # Additional headless-specific settings
                options.add_argument("--enable-javascript")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument(
                    "--enable-features=NetworkService,NetworkServiceInProcess"
                )
                # Emulate a proper display
                options.add_argument("--force-device-scale-factor=1")
            else:
                options.add_argument("--start-maximized")

            # Common options
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-notifications")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("prefs", prefs)

            if not self.debug:
                options.add_argument("--disable-logging")
                options.add_argument("--log-level=3")

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

            # Apply stealth settings
            stealth(
                self.driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )

            # Ensure proper window size and zoom
            if self.headless:
                # Force a specific window size and zoom level in headless mode
                self.driver.execute_cdp_cmd(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": 1920,
                        "height": 1080,
                        "deviceScaleFactor": 1.0,
                        "mobile": False,
                    },
                )
                # Set proper zoom level
                self.driver.execute_script("document.body.style.zoom = '100%'")
            else:
                self.driver.maximize_window()

            if self.debug:
                self.logger.debug("Browser session initialized with selenium-stealth")

        except Exception as e:
            if self.debug:
                self.logger.error(f"Error setting up driver: {str(e)}")
            raise

    def _ensure_element_visible(self, element):
        """Ensure element is visible and clickable in both headless and normal modes"""
        try:
            # Scroll element into view
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            time.sleep(0.5)  # Allow time for scrolling

            # Try to remove any overlays or popups that might be in the way
            self.driver.execute_script("""
                var elements = document.getElementsByClassName('overlay');
                for(var i=0; i<elements.length; i++){
                    elements[i].style.display = 'none';
                }
            """)

            # Ensure element is visible and clickable
            if not element.is_displayed() or not element.is_enabled():
                self.driver.execute_script(
                    "arguments[0].style.display = 'block';", element
                )
                self.driver.execute_script(
                    "arguments[0].style.visibility = 'visible';", element
                )
                self.driver.execute_script("arguments[0].style.opacity = '1';", element)

            return True
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error ensuring element visibility: {str(e)}")
            return False

    def _wait_and_click(self, element, timeout=10):
        """Wait for element to be clickable and click it safely"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, element))
            )
            element = self.driver.find_element(By.XPATH, element)
            self._ensure_element_visible(element)
            element.click()
            return True
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error clicking element: {str(e)}")
            return False

    def _load_config(self):
        """Load configuration from config.json"""
        try:
            config_path = "config.json"
            if not os.path.exists(config_path):
                if self.debug:
                    self.logger.debug("No config file found, will use manual login")
                return None

            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error loading config: {str(e)}")
            return None

    def _save_debug_info(self, driver, stage_name, url=None):
        """Save debug information at various stages"""
        if not self.debug:
            return

        try:
            # Get page source and screenshot
            html_content = driver.page_source
            screenshot = driver.get_screenshot_as_png()

            # Log error with both HTML and screenshot
            self.error_logger.log_error(
                f"Debug info for stage: {stage_name}",
                html=html_content,
                screenshot=screenshot,
                url=url,
            )

        except Exception as e:
            self.logger.error(f"Failed to save debug info: {str(e)}")

    def _wait_for_page_load(self, timeout=None):
        """Enhanced page load detection"""
        if timeout is None:
            timeout = self.page_load_timeout

        start_time = time.time()
        last_height = 0
        stable_count = 0

        try:
            # First wait for document ready
            WebDriverWait(self.driver, timeout / 2).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            # Then monitor for content stability
            while time.time() - start_time < timeout:
                current_height = self.driver.execute_script(
                    "return document.documentElement.scrollHeight"
                )

                if current_height == last_height:
                    stable_count += 1
                    if stable_count >= 3:  # Content height stable for 3 checks
                        break
                else:
                    stable_count = 0
                    last_height = current_height

                time.sleep(self.polling_interval)

            # Brief final wait for any last dynamic content
            time.sleep(self.min_wait)
            return True

        except Exception as e:
            if self.debug:
                self.logger.error(f"Error waiting for page load: {str(e)}")
            return False

    def check_login(self):
        """Check if current session is valid"""
        try:
            if not self.driver:
                return False

            # First try accessing main page with proper wait
            self.driver.get(self.BASE_URL)
            if not self._wait_for_page_load():
                if self.debug:
                    self.logger.debug("Page failed to load completely")
                return False

            # Check if redirected to login page
            if "dang-nhap" in self.driver.current_url.lower():
                if self.debug:
                    self.logger.debug("Redirected to login page")
                return False

            # Look for logged-in indicators with better waiting
            try:
                # First check for logout elements with explicit wait
                try:
                    logout_element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                "//a[contains(@href, 'dang-xuat')] | //span[contains(text(), 'Đăng xuất')]",
                            )
                        )
                    )
                    if logout_element and logout_element.is_displayed():
                        return True
                except (TimeoutException, WebDriverException):
                    pass

                # Then check for account menu or user profile indicators
                account_indicators = [
                    "//a[contains(@href, '/tai-khoan')]",
                    "//span[contains(text(), 'Tài khoản')]",
                    "//a[contains(@href, '/trang-ca-nhan')]",
                ]

                for indicator in account_indicators:
                    try:
                        element = WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, indicator))
                        )
                        if element and element.is_displayed():
                            return True
                    except TimeoutException:
                        continue

                # Finally check for absence of login elements
                login_elements = self.driver.find_elements(
                    By.XPATH,
                    "//span[contains(text(),'Đăng nhập')] | //span[contains(text(),'Đăng ký')]",
                )

                if not login_elements:
                    return True

                # If we found login elements, verify they're actually visible
                return not any(elem.is_displayed() for elem in login_elements)

            except Exception as e:
                if self.debug:
                    self.logger.error(f"Error checking login elements: {str(e)}")
                return False

            if self.debug:
                self.logger.debug("No clear login status found, capturing page")
                self.driver.save_screenshot("login_check_failure.png")
                capture_page_source(self.driver, "failed_login_check.html")
            return False

        except Exception as e:
            if self.debug:
                self.logger.error(f"Login check error: {str(e)}")
            return False

    def check_page_status(self, url=None):
        """Check for common page errors"""
        try:
            if not url:
                url = self.driver.current_url

            # Check for 404 URL directly
            if "/404.html" in url:
                if self.debug:
                    self.logger.debug(f"404 detected in URL: {url}")
                return "404"

            # Check page content
            page_content = self.driver.page_source.lower()

            # Check for 404 markers
            if any(
                marker.lower() in page_content for marker in self.ERROR_MARKERS["404"]
            ):
                if self.debug:
                    self.logger.debug(f"404 detected in page content: {url}")
                return "404"

            # Check for login required
            if any(
                marker.lower() in page_content
                for marker in self.ERROR_MARKERS["login_required"]
            ):
                if self.debug:
                    self.logger.debug(f"Login required detected: {url}")
                return "login_required"

            return "ok"

        except Exception as e:
            if self.debug:
                self.logger.error(f"Error checking page status: {str(e)}")
            return "error"

    def _clean_cookie(self, cookie):
        """Clean and validate cookie data before adding to session"""
        try:
            # Ensure domain is valid for luatvietnam.vn
            if "domain" in cookie:
                if not cookie["domain"].endswith("luatvietnam.vn"):
                    cookie["domain"] = ".luatvietnam.vn"
            else:
                cookie["domain"] = ".luatvietnam.vn"

            # Remove problematic keys that might cause issues
            keys_to_remove = ["sameSite", "storeId", "id"]
            for key in keys_to_remove:
                cookie.pop(key, None)

            # Ensure required fields are present
            required_fields = ["name", "value", "domain"]
            if not all(field in cookie for field in required_fields):
                if self.debug:
                    self.logger.debug(f"Cookie missing required fields: {cookie}")
                return None

            return cookie
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error cleaning cookie: {str(e)}")
            return None

    def load_cookies(self):
        """Load and validate cookies from pickle file"""
        try:
            if not os.path.exists("lawvn_cookies.pkl"):
                if self.debug:
                    self.logger.debug("No cookie file found")
                return False

            with open("lawvn_cookies.pkl", "rb") as f:
                cookies = pickle.load(f)

            if not cookies:
                if self.debug:
                    self.logger.debug("Empty cookies file")
                return False

            # First navigate to base URL to set correct domain context
            self.driver.get(self.BASE_URL)
            time.sleep(1)

            # Check if any cookies are expired and clean them
            current_time = time.time()
            valid_cookies = []
            for cookie in cookies:
                # Clean and validate cookie
                cleaned_cookie = self._clean_cookie(cookie)
                if not cleaned_cookie:
                    continue

                # Skip cookies with expiry in the past
                if "expiry" in cleaned_cookie:
                    if cleaned_cookie["expiry"] <= current_time:
                        if self.debug:
                            self.logger.debug(
                                f"Skipping expired cookie: {cleaned_cookie['name']}"
                            )
                        continue

                valid_cookies.append(cleaned_cookie)

            if not valid_cookies:
                if self.debug:
                    self.logger.debug("No valid cookies found")
                return False

            # Add valid cookies to session
            success_count = 0
            for cookie in valid_cookies:
                try:
                    self.driver.add_cookie(cookie)
                    success_count += 1
                except Exception as e:
                    if self.debug:
                        self.logger.error(
                            f"Error adding cookie {cookie['name']}: {str(e)}"
                        )

            if self.debug:
                self.logger.debug(
                    f"Successfully added {success_count} of {len(valid_cookies)} cookies"
                )

            return success_count > 0

        except Exception as e:
            if self.debug:
                self.logger.error(f"Error loading cookies: {str(e)}")
            return False

    def save_cookies(self):
        """Save current cookies to pickle file"""
        try:
            cookies = self.driver.get_cookies()
            # Clean cookies before saving
            valid_cookies = [self._clean_cookie(cookie) for cookie in cookies if cookie]
            valid_cookies = [c for c in valid_cookies if c]  # Remove None values

            if valid_cookies:
                with open("lawvn_cookies.pkl", "wb") as f:
                    pickle.dump(valid_cookies, f)
                if self.debug:
                    self.logger.debug(f"Saved {len(valid_cookies)} cookies")
                return True
            return False

        except Exception as e:
            if self.debug:
                self.logger.error(f"Error saving cookies: {str(e)}")
            return False

    def find_document_links(self, url, debug=False):
        """Optimized document link detection"""
        if not url or not self.driver:
            return []

        try:
            # Set page load timeout
            self.driver.set_page_load_timeout(self.page_load_timeout)

            # Load the page
            self.driver.get(url)

            # Wait for initial load with shorter timeout
            if not self._wait_for_page_load(timeout=10):
                if debug:
                    self.logger.debug(
                        "Initial page load timeout, checking content anyway"
                    )

            # Check if redirect occurred and wait for download elements
            if "luatvietnam.vn" in self.driver.current_url:
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "div.list-download")
                        )
                    )
                except TimeoutException:
                    if debug:
                        self.logger.debug("Download section not found")
                    return []
                except WebDriverException as e:
                    if debug:
                        self.logger.debug(
                            f"WebDriver error waiting for download section: {e}"
                        )
                    return []

            # Check if redirected to main page
            if (
                "luatvietnam.vn" in self.driver.current_url.lower()
                and "dang-nhap" not in self.driver.current_url.lower()
            ):
                if self.debug:
                    self.logger.debug(
                        f"Redirected to main page from {url} to {self.driver.current_url}"
                    )
                    capture_page_source(self.driver, "redirected_page_source.html")
                self.driver.get(url)
                time.sleep(2)

            # Check page status first
            status = self.check_page_status(url)
            if status == "404":
                if self.debug:
                    self.logger.error(f"Page not found: {url}")
                return []
            elif status == "login_required":
                if self.debug:
                    self.logger.debug(f"Login required detected: {url}")
                    capture_page_source(self.driver, "login_required_page_source.html")
                if not self.check_login():
                    if self.debug:
                        self.logger.error("Login failed after detection")
                    return []

                # Retry fetching the URL after login
                if not retry_fetch_url(self.driver, url, debug=self.debug):
                    if self.debug:
                        self.logger.error(
                            "Page still not accessible after login retries"
                        )
                    return []

            # Extract links using provided XPath expressions
            doc_links = []
            doc_elements = self.driver.find_elements(
                By.CSS_SELECTOR, "div.list-download a[title='Bản Word (.doc)']"
            )
            pdf_elements = self.driver.find_elements(
                By.CSS_SELECTOR, "div.list-download a[title='Bản PDF (.pdf)']"
            )

            # Extract document ID and name from URL
            doc_id = None
            doc_name = None
            if "-d" in url:
                base_url = url.split("#")[0]  # Remove any fragments
                doc_name = format_document_name(base_url)
                doc_id = url.split("-d")[-1].split(".")[0]

            if not doc_name:
                return []  # Exit if we can't get the base document name

            # Use the same base name for both DOC and PDF
            for elem in doc_elements:
                href = elem.get_attribute("href")
                if href:
                    doc_links.append(
                        {
                            "url": href,
                            "type": "doc",
                            "title": f"{doc_name}.docx",  # Use base name + extension
                            "text": elem.text,
                            "doc_id": doc_id,
                        }
                    )
                    if self.debug:
                        self.logger.debug(f"Found DOC link: {href}")

            for elem in pdf_elements:
                href = elem.get_attribute("href")
                if href:
                    doc_links.append(
                        {
                            "url": href,
                            "type": "pdf",
                            "title": f"{doc_name}.pdf",  # Use base name + extension
                            "text": elem.text,
                            "doc_id": doc_id,
                        }
                    )
                    if self.debug:
                        self.logger.debug(f"Found PDF link: {href}")

            return doc_links

        except TimeoutException as e:
            if debug:
                self.logger.error(f"Timeout finding links: {e}")
            return []
        except WebDriverException as e:
            if debug:
                self.logger.error(f"WebDriver error finding links: {e}")
            return []
        except Exception as e:
            if debug:
                self.logger.error(f"Error finding links: {e}")
            return []

    def login(self, force=False):
        """Perform login using saved credentials"""
        if not force and self.check_login():
            return True

        if not self.driver:
            self.setup_driver()

        try:
            # First try using saved cookies
            if not force and os.path.exists("lawvn_cookies.pkl"):
                self.driver.get(self.BASE_URL)
                if self.load_cookies():
                    self.driver.refresh()
                    time.sleep(2)
                    if self.check_login():
                        if self.debug:
                            self.logger.debug("Login successful using saved cookies")
                        return True
                    if self.debug:
                        self.logger.debug(
                            "Saved cookies are invalid, proceeding with normal login"
                        )

            self.driver.get(self.BASE_URL)
            time.sleep(2)  # Increased wait time for headless mode

            # Click login button with improved handling
            login_xpath = "//span[contains(text(),'/ Đăng nhập')]"
            if not self._wait_and_click(login_xpath):
                raise Exception("Could not click login button")

            if self.config and "google_credentials" in self.config:
                login_successful = self._do_google_login()
                if login_successful:
                    # Save cookies after successful login
                    self.save_cookies()
                return login_successful
            else:
                print("No credentials found in config.json")
                return False

        except Exception as e:
            if self.debug:
                self.logger.error(f"Login error: {str(e)}")
            return False

    def _do_google_login(self):
        """Handle Google login using selenium-stealth"""
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                if self.debug:
                    self.logger.debug(f"Login attempt {attempt + 1} of {max_retries}")

                creds = self.config["google_credentials"]
                original_window = self.driver.current_window_handle

                # Enhanced waiting and clicking for Google login button
                google_btn = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.login-google"))
                )
                self._ensure_element_visible(google_btn)
                google_btn.click()
                time.sleep(2)

                try:
                    # Wait for new window and switch to it
                    WebDriverWait(self.driver, 10).until(
                        lambda d: len(d.window_handles) > 1
                    )
                    for window_handle in self.driver.window_handles:
                        if window_handle != original_window:
                            self.driver.switch_to.window(window_handle)
                            break

                    # Enter email
                    email_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, 'input[type="email"]')
                        )
                    )
                    email_input.clear()
                    email_input.send_keys(creds["email"])
                    email_input.send_keys(Keys.RETURN)
                    time.sleep(2)

                    # Wait for password field
                    password_input = WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located(
                            (
                                By.CSS_SELECTOR,
                                'input[type="password"].whsOnd.zHQkBf[jsname="YPqjbf"]',
                            )
                        )
                    )

                    # Make sure it's clickable
                    WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(
                            (
                                By.CSS_SELECTOR,
                                'input[type="password"].whsOnd.zHQkBf[jsname="YPqjbf"]',
                            )
                        )
                    )

                    # Focus and enter password
                    self.driver.execute_script("arguments[0].focus();", password_input)
                    time.sleep(1)
                    password_input.clear()
                    password_input.send_keys(creds["password"])
                    time.sleep(1)

                    # Click the Next button
                    next_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable(
                            (
                                By.CSS_SELECTOR,
                                'button[jsname="LgbsSe"].VfPpkd-LgbsSe-OWXEXe-k8QpJ',
                            )
                        )
                    )
                    next_button.click()
                    time.sleep(3)

                finally:
                    # Switch back to main window
                    if original_window in self.driver.window_handles:
                        self.driver.switch_to.window(original_window)

                # Wait and refresh
                time.sleep(2)
                self.driver.refresh()
                time.sleep(2)

                # Verify login success
                if self.check_login():
                    if self.debug:
                        self.logger.debug(f"Login successful on attempt {attempt + 1}")
                    print("Login successful")
                    return True

                if self.debug:
                    self.logger.debug(
                        f"Login verification failed on attempt {attempt + 1}"
                    )

                # If not successful and more retries left, setup a fresh driver
                if attempt < max_retries - 1:
                    if self.debug:
                        self.logger.debug("Refreshing driver for next attempt")
                    self.driver.quit()
                    self.setup_driver()
                    time.sleep(retry_delay)

            except Exception as e:
                if self.debug:
                    self._save_debug_info(
                        self.driver, f"login_error_attempt{attempt + 1}"
                    )
                    self.logger.error(f"Login error on attempt {attempt + 1}: {str(e)}")
                    try:
                        self.driver.save_screenshot(
                            f"login_error_attempt{attempt + 1}.png"
                        )
                        with open(
                            f"login_error_attempt{attempt + 1}.html",
                            "w",
                            encoding="utf-8",
                        ) as f:
                            f.write(self.driver.page_source)
                    except (WebDriverException, IOError) as e:
                        if self.debug:
                            self.logger.debug(f"Failed to save debug info: {str(e)}")
                        pass

                # If more retries left, setup fresh driver and continue
                if attempt < max_retries - 1:
                    if self.debug:
                        self.logger.debug("Refreshing driver for next attempt")
                    try:
                        self.driver.quit()
                    except WebDriverException:
                        pass
                    self.setup_driver()
                    time.sleep(retry_delay)
                    continue

        return False

    def __del__(self):
        """Clean up browser session"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                if self.debug:
                    self.logger.error(f"Error during driver cleanup: {str(e)}")
                pass
