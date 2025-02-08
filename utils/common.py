import logging
import logging.handlers
import contextlib
import sys
import os
from collections import defaultdict
import time

def setup_logger(debug=False):
    """Setup logger with file and console output"""
    class CleanFormatter(logging.Formatter):
        def format(self, record):
            # Remove selenium debugging noise
            if 'selenium' in record.name.lower() and record.levelno < logging.WARNING:
                return ""
            if 'urllib3' in record.name.lower() and record.levelno < logging.WARNING:
                return ""
                
            # Clean up common noise in messages
            msg = record.getMessage()
            if 'http://localhost' in msg:
                return ""
            if 'Remote response' in msg:
                return ""
            if 'Finished Request' in msg:
                return ""
            
            # Format timestamp without milliseconds
            record.asctime = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
            return f"{record.asctime} - {record.levelname} - {record.getMessage()}"

    logger = logging.getLogger(__name__)
    logger.handlers = []  # Clear existing handlers

    # Set up file handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        'crawler.log',
        maxBytes=1024*1024,  # 1MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(CleanFormatter())

    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(CleanFormatter())

    # Set logging levels based on debug flag
    if debug:
        logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
        file_handler.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
        console_handler.setLevel(logging.INFO)
        file_handler.setLevel(logging.INFO)

    # Set third party loggers to higher level
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

def hide_prints():
    """Context manager to hide print statements"""
    class DummyFile:
        def write(self, x): pass
        def flush(self): pass
    
    @contextlib.contextmanager
    def silent_prints():
        save_stdout = sys.stdout
        sys.stdout = DummyFile()
        try:
            yield
        finally:
            sys.stdout = save_stdout
    
    return silent_prints()

def save_debug_html(url, content, folder="debug"):
    """Save HTML content for debugging"""
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    # Create a safe filename from the URL
    safe_url = url.split('//')[-1].replace('/', '_')
    filepath = os.path.join(folder, f"{safe_url}.html")
    
    # Save the content
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logging.debug(f"Saved debug HTML to {filepath}")
    except Exception as e:
        logging.error(f"Failed to save debug HTML: {str(e)}")

def capture_page_source(driver, filename="page_source.html"):
    """Capture the current page source for debugging purposes"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        logging.debug(f"Captured page source to {filename}")
    except Exception as e:
        logging.error(f"Failed to capture page source: {str(e)}")

def retry_fetch_url(driver, url, retries=3, delay=2, debug=False):
    """Retry fetching the URL after login"""
    for attempt in range(retries):
        try:
            driver.get(url)
            time.sleep(delay)
            if 'dang-nhap' not in driver.current_url.lower():
                return True
        except Exception as e:
            if debug:
                logging.error(f"Retry {attempt + 1} failed: {str(e)}")
            time.sleep(delay)
    return False

class DownloadStats:
    def __init__(self):
        self.success_count = defaultdict(int)
        self.total_files = 0
        self.successful = []
        self.failed = []
    
    def add_success(self, file_type):
        """Record a successful download by file type"""
        self.success_count[file_type] += 1
        self.total_files += 1
    
    def add_failure(self, url, error):
        """Record a failed download"""
        self.failed.append((url, str(error)))
    
    def add_download(self, url, filepath, success=True, error=None):
        """Record a download attempt with full details"""
        if success:
            self.successful.append((url, filepath))
            ext = os.path.splitext(filepath)[1].lower()
            self.add_success(ext)
        else:
            self.add_failure(url, error)
    
    def get_summary(self):
        """Get download statistics summary"""
        return {
            'doc': self.success_count.get('.doc', 0) + self.success_count.get('.docx', 0),
            'pdf': self.success_count.get('.pdf', 0),
            'total': self.total_files,
            'successful': self.successful,
            'failed': self.failed
        }

def check_setup_and_confirm():
    """Check setup status and get user confirmation"""
    from crawl.verifier import check_missing_downloads  # Import here to avoid circular dependency
    
    setup_status = {
        'cookies': os.path.exists('lawvn_cookies.pkl'),
        'batches': os.path.exists('batches'),
        'excel_files': [],
    }
    
    if setup_status['batches']:
        setup_status['excel_files'] = [f for f in os.listdir('batches') if f.endswith(('.xlsx', '.xls'))]
    
    print("\nSetup Status:")
    print(f"- Login cookies: {'✓' if setup_status['cookies'] else '✗'}")
    print(f"- Batches folder: {'✓' if setup_status['batches'] else '✗'}")
    print(f"- Excel files: {len(setup_status['excel_files'])} found")
    
    if not all([
        setup_status['cookies'],
        setup_status['batches'],
        len(setup_status['excel_files']) > 0
    ]):
        print("\nMissing required setup:")
        if not setup_status['cookies']:
            print("- Please run 'python login.py' first")
        if not setup_status['batches']:
            print("- Create 'batches' folder")
        if not setup_status['excel_files']:
            print("- Add Excel files to 'batches' folder")
        return False
    
    print("\nCrawl Options:")
    print("1. Check for missing files and resume")
    print("2. Start fresh crawl (ignore previous progress)")
    print("3. Exit")
    
    while True:
        choice = input("\nEnter your choice (1-3): ").strip()
        if choice == '1':
            missing_downloads = check_missing_downloads()
            if missing_downloads:
                print(f"\nFound {len(missing_downloads)} missing files.")
                print("\nChoose action:")
                print("1. Download only missing files")
                print("2. Restart complete crawl")
                print("3. Exit")
                
                subchoice = input("\nEnter your choice (1-3): ").strip()
                if subchoice == '1':
                    return {'action': 'retry', 'resume': True}
                elif subchoice == '2':
                    return {'action': 'fresh', 'resume': False}
                else:
                    return {'action': 'exit'}
            else:
                print("\nNo missing files found!")
                if input("Start fresh crawl anyway? (yes/no): ").lower() == 'yes':
                    return {'action': 'fresh', 'resume': False}
                return {'action': 'exit'}
                
        elif choice == '2':
            return {'action': 'fresh', 'resume': False}
        elif choice == '3':
            return {'action': 'exit'}
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")
