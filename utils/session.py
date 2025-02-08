import os
import time
import pickle
import logging
import requests
import random
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from utils.common import setup_logger
from utils.common import capture_page_source, retry_fetch_url  # Add this import
from utils.document_formatter import format_document_name  # Add this import

class LawVNSession:
    BASE_URL = "https://luatvietnam.vn"
    LOGIN_URL = f"{BASE_URL}/dang-nhap.html"

    def __init__(self, debug=False, headless=True):
        self.debug = debug
        self.headless = headless
        self.logger = setup_logger(debug)
        self.config = self._load_config()
        self.driver = None
        self.setup_driver()
        self.ERROR_MARKERS = {
            '404': [
                'cat-box-404',
                'Không tìm thấy trang',
                'URL không tồn tại',
                '/404.html'
            ],
            'login_required': [
                'lawsVnLogin',
                'Quý khách vui lòng đăng nhập',
                'tooltip-text-2',
                'class="btn-login"'
            ]
        }

    def setup_driver(self):
        """Initialize browser session with selenium-stealth"""
        try:
            options = Options()
            
            if self.headless:
                options.add_argument('--headless')
                options.add_argument('--window-size=1920,1080')
            
            # Common options
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            if not self.debug:
                options.add_argument('--disable-logging')
                options.add_argument('--log-level=3')

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

            # Apply stealth settings
            stealth(self.driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )

            # Set window size
            if not self.headless:
                self.driver.maximize_window()
            
            if self.debug:
                self.logger.debug("Browser session initialized with selenium-stealth")
                
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error setting up driver: {str(e)}")
            raise

    def _load_config(self):
        """Load configuration from config.json"""
        try:
            config_path = 'config.json'
            if not os.path.exists(config_path):
                if self.debug:
                    self.logger.debug("No config file found, will use manual login")
                return None
                
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            if self.debug:
                self.logger.error(f"Error loading config: {str(e)}")
            return None

    def _save_debug_info(self, driver, stage_name):
        """Save debug information at various stages"""
        if not self.debug:
            return

        timestamp = time.strftime("%H%M%S")
        prefix = f"{stage_name}_{timestamp}"
        
        if stage_name in ['login_error', 'google_login', 'verification_failed']:
            screenshot_path = os.path.join(self.debug_dir, f"{prefix}_screen.png")
            driver.save_screenshot(screenshot_path)
            source_path = os.path.join(self.debug_dir, f"{prefix}_source.html")
            with open(source_path, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            self.logger.debug(f"Saved {stage_name} debug info")

    def check_login(self):
        """Check if current session is valid"""
        try:
            # First check if we have a valid browser session
            if not self.driver:
                if self.debug:
                    self.logger.debug("No browser session found")
                return False

            # Ensure the window is still open
            if len(self.driver.window_handles) == 0:
                if self.debug:
                    self.logger.debug("No open windows found")
                return False

            # Switch to the main window if multiple windows are open
            if len(self.driver.window_handles) > 1:
                self.driver.switch_to.window(self.driver.window_handles[0])

            # Try accessing member page
            try:
                time.sleep(1)  # Give page time to load
                
                # Check if the window is still open
                if len(self.driver.window_handles) == 0:
                    if self.debug:
                        self.logger.debug("No open windows found after switching")
                    return False

                # Check URL and content for login indicators
                login_successful = (
                    'dang-nhap' not in self.driver.current_url.lower() and
                    any(x in self.driver.page_source for x in ['Đăng xuất', 'Tài khoản của tôi', 'Trang cá nhân'])
                )
                
                if not login_successful:
                    # Alternative check: Ensure "Đăng nhập" or "Đăng ký" elements are not present
                    login_elements = self.driver.find_elements(By.XPATH, "//span[@class='m-hide'][contains(text(),'Đăng ký')] | //span[@class='btn-login']//span[1]")
                    login_successful = len(login_elements) == 0
                
                if self.debug:
                    capture_page_source(self.driver, "login_check_page_source.html")
                    self.logger.debug(f"Login check result: {login_successful}")
                    if not login_successful:
                        self.logger.debug("Login indicators not found")
                        
                return login_successful

            except Exception as e:
                if self.debug:
                    self.logger.error(f"Error checking member page: {str(e)}")
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
            if '/404.html' in url:
                if self.debug:
                    self.logger.debug(f"404 detected in URL: {url}")
                return '404'

            # Check page content
            page_content = self.driver.page_source.lower()
            
            # Check for 404 markers
            if any(marker.lower() in page_content for marker in self.ERROR_MARKERS['404']):
                if self.debug:
                    self.logger.debug(f"404 detected in page content: {url}")
                return '404'
                
            # Check for login required
            if any(marker.lower() in page_content for marker in self.ERROR_MARKERS['login_required']):
                if self.debug:
                    self.logger.debug(f"Login required detected: {url}")
                return 'login_required'
                
            return 'ok'

        except Exception as e:
            if self.debug:
                self.logger.error(f"Error checking page status: {str(e)}")
            return 'error'

    def find_document_links(self, url, debug=False):
        """Find document links using browser session"""
        if not url or not self.driver:
            return []

        try:
            self.driver.get(url)
            time.sleep(2)  # Wait for page load

            # Check if redirected to main page
            if 'luatvietnam.vn' in self.driver.current_url.lower() and 'dang-nhap' not in self.driver.current_url.lower():
                if self.debug:
                    self.logger.debug(f"Redirected to main page from {url} to {self.driver.current_url}")
                    capture_page_source(self.driver, "redirected_page_source.html")
                self.driver.get(url)
                time.sleep(2)

            # Check page status first
            status = self.check_page_status(url)
            if status == '404':
                if self.debug:
                    self.logger.error(f"Page not found: {url}")
                return []
            elif status == 'login_required':
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
                        self.logger.error("Page still not accessible after login retries")
                    return []

            # Extract links using provided XPath expressions
            doc_links = []
            doc_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.list-download a[title='Bản Word (.doc)']")
            pdf_elements = self.driver.find_elements(By.CSS_SELECTOR, "div.list-download a[title='Bản PDF (.pdf)']")
            
            # Extract document ID and name from URL
            doc_id = None
            doc_name = None
            if '-d' in url:
                base_url = url.split('#')[0]  # Remove any fragments
                doc_name = format_document_name(base_url)
                doc_id = url.split('-d')[-1].split('.')[0]
            
            if not doc_name:
                return []  # Exit if we can't get the base document name

            # Use the same base name for both DOC and PDF
            for elem in doc_elements:
                href = elem.get_attribute('href')
                if href:
                    doc_links.append({
                        'url': href,
                        'type': 'doc',
                        'title': f"{doc_name}.docx",  # Use base name + extension
                        'text': elem.text,
                        'doc_id': doc_id
                    })
                    if self.debug:
                        self.logger.debug(f"Found DOC link: {href}")

            for elem in pdf_elements:
                href = elem.get_attribute('href')
                if href:
                    doc_links.append({
                        'url': href,
                        'type': 'pdf',
                        'title': f"{doc_name}.pdf",  # Use base name + extension
                        'text': elem.text,
                        'doc_id': doc_id
                    })
                    if self.debug:
                        self.logger.debug(f"Found PDF link: {href}")

            return doc_links

        except Exception as e:
            if self.debug:
                self.logger.error(f"Error finding links: {str(e)}")
            return []

    def login(self, force=False):
        """Perform login using saved credentials"""
        if not force and self.check_login():
            return True

        if not self.driver:
            self.setup_driver()

        try:
            self.driver.get(self.BASE_URL)
            time.sleep(1)

            # Click login button
            login_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'/ Đăng nhập')]"))
            )
            login_button.click()
            time.sleep(1)

            if self.config and 'google_credentials' in self.config:
                return self._do_google_login()
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
                
                creds = self.config['google_credentials']
                original_window = self.driver.current_window_handle
                
                # Click Google login button on main site
                google_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.login-google'))
                )
                google_btn.click()
                time.sleep(2)

                try:
                    # Wait for new window and switch to it
                    WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
                    for window_handle in self.driver.window_handles:
                        if window_handle != original_window:
                            self.driver.switch_to.window(window_handle)
                            break

                    # Enter email
                    email_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
                    )
                    email_input.clear()
                    email_input.send_keys(creds['email'])
                    email_input.send_keys(Keys.RETURN)
                    time.sleep(2)
                    
                    # Wait for password field
                    password_input = WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 
                            'input[type="password"].whsOnd.zHQkBf[jsname="YPqjbf"]'))
                    )
                    
                    # Make sure it's clickable
                    WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 
                            'input[type="password"].whsOnd.zHQkBf[jsname="YPqjbf"]'))
                    )
                    
                    # Focus and enter password
                    self.driver.execute_script("arguments[0].focus();", password_input)
                    time.sleep(1)
                    password_input.clear()
                    password_input.send_keys(creds['password'])
                    time.sleep(1)
                    
                    # Click the Next button
                    next_button = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR,
                            'button[jsname="LgbsSe"].VfPpkd-LgbsSe-OWXEXe-k8QpJ'))
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
                    self.logger.debug(f"Login verification failed on attempt {attempt + 1}")
                
                # If not successful and more retries left, setup a fresh driver
                if attempt < max_retries - 1:
                    if self.debug:
                        self.logger.debug("Refreshing driver for next attempt")
                    self.driver.quit()
                    self.setup_driver()
                    time.sleep(retry_delay)

            except Exception as e:
                if self.debug:
                    self.logger.error(f"Login error on attempt {attempt + 1}: {str(e)}")
                    try:
                        self.driver.save_screenshot(f'login_error_attempt{attempt + 1}.png')
                        with open(f'login_error_attempt{attempt + 1}.html', 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                    except:
                        pass
                
                # If more retries left, setup fresh driver and continue
                if attempt < max_retries - 1:
                    if self.debug:
                        self.logger.debug("Refreshing driver for next attempt")
                    try:
                        self.driver.quit()
                    except:
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
            except:
                pass
