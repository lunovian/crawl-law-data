import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from lxml import html
import logging
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pickle
import time
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import logging.handlers
from selenium_stealth import stealth  # Add this import
import concurrent.futures
import psutil  # Add this import
import tempfile
from filelock import FileLock
import hashlib
from concurrent.futures import ThreadPoolExecutor
import signal
import atexit
import sys
import portalocker  # Add this import for better cross-process file locking
import contextlib
from utils.document_formatter import format_document_name
from utils import BatchProcessor, get_user_workers
from utils.common import setup_logger
from crawl.processor import BatchProcessor, get_user_workers
from crawl.downloader import download_file  # Add this import
import re

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

    file_handler = logging.handlers.RotatingFileHandler(
        'crawler.log',
        maxBytes=1024*1024,  # 1MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(CleanFormatter())

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(CleanFormatter())

    if debug:
        logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
        file_handler.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)  # Change from ERROR to WARNING
        console_handler.setLevel(logging.WARNING)  # Change from ERROR to WARNING 
        file_handler.setLevel(logging.WARNING)  # Change from ERROR to WARNING

    # Set third party loggers to higher level
    logging.getLogger('selenium').setLevel(logging.ERROR)  # Increase severity
    logging.getLogger('urllib3').setLevel(logging.ERROR)  # Increase severity
    logging.getLogger('requests').setLevel(logging.ERROR)  # Increase severity

    return logger

def save_debug_html(url, content, folder="debug"):
    """Save HTML content for debugging"""
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    safe_url = url.split('//')[-1].replace('/', '_')
    filepath = os.path.join(folder, f"{safe_url}.html")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    logging.debug(f"Saved HTML content to {filepath}")

class DownloadStatus:
    def __init__(self):
        self.successful = []
        self.failed = []

    def add_success(self, url, filepath):
        self.successful.append((url, filepath))

    def add_failure(self, url, error):
        self.failed.append((url, str(error)))

    def get_summary(self):
        return {
            'successful': self.successful,
            'failed': self.failed
        }

def download_worker(args):
    """Modified worker function to support retry mode"""
    url, filename, folder, retry_mode = args
    formatted_filename = format_document_name(filename)
    success, error = download_file(url, formatted_filename, folder, retry_mode)
    return (url, formatted_filename, folder, success, error)

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

def download_files_parallel(urls, filenames, folders, max_workers=None, batch_size=5, retry_mode=False):
    """Download multiple files in parallel with batching and deduplication"""
    # Only get user input if max_workers is None and we haven't asked before
    if max_workers is None and not hasattr(download_files_parallel, 'cached_workers'):
        download_files_parallel.cached_workers = get_user_workers()
    
    if max_workers is None:
        max_workers = download_files_parallel.cached_workers
    
    processor = BatchProcessor(batch_size=batch_size, max_workers=max_workers)
    status = DownloadStatus()
    
    # Create batches of download tasks
    tasks = [(url, filename, folder, retry_mode) 
            for url, filename, folder in zip(urls, filenames, folders)]
    
    print(f"Using {max_workers} workers")

    results = []
    with hide_prints():  # Hide detailed download messages
        for batch in processor.process_batches(tasks):
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                batch_results = list(executor.map(download_worker, batch))
                results.extend(batch_results)
                
                for url, filename, folder, success, error in batch_results:
                    filepath = os.path.join(folder, filename)
                    if success:
                        status.add_success(url, filepath)
                    else:
                        status.add_failure(url, error)
                    
        # Small delay between batches
        time.sleep(0.5)
    
    # Print summary after all batches
    if status.successful:
        print("\nSuccessfully downloaded:")
        for url, filepath in status.successful:
            print(f"✓ {os.path.basename(filepath)} from {url}")
    
    if status.failed:
        print("\nFailed downloads:")
        for url, error in status.failed:
            print(f"✗ {url} - Error: {error}")
            
    return [r[3] for r in results], status

# Add global lock tracking
active_locks = set()

def find_document_links(url, debug=False, session=None):
    """Find document download links in a page"""
    logger = setup_logger(debug)
    # Append "#taive" if missing to move to the download tab
    if "#taive" not in url:
        url += "#taive"
        if debug:
            logger.debug("Appended #taive to url to move to the download tab")
    max_retries = 3
    retry_delay = 2
    
    def debug_log(msg):
        """Only log if debug is enabled"""
        if debug:
            logger.debug(msg)
    
    # Ensure logged in before attempting to fetch documents
    if session and not session.check_login():
        logger.error("Not logged in. Please login first")
        return []
    
    for attempt in range(max_retries):
        try:
            log_url = url.split('#')[0]
            debug_log(f"Processing URL: {log_url}")
            
            requests_session = session.session if session else requests.Session()
            response = requests_session.get(url, allow_redirects=True)
            
            if response.status_code == 404:
                logger.error(f"Got 404 error on attempt {attempt + 1}. URL: {url}")
                if session and attempt < max_retries - 1:
                    debug_log("Attempting to refresh session...")
                    session.login()
                    time.sleep(retry_delay)
                    continue
                    
            if debug:
                save_debug_html(log_url, response.text)
            
            if 'dang-nhap' in response.url or 'luatvietnam.vn' in response.url:
                logger.error("Redirected to login page or main page - session may have expired")
                if session and not session.check_login():
                    session.login()
                    time.sleep(retry_delay)
                    response = requests_session.get(url, allow_redirects=True)
                    if 'dang-nhap' in response.url or 'luatvietnam.vn' in response.url:
                        return []
                    else:
                        response = requests_session.get(url, allow_redirects=True)
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract document title and create links list with title info
            title_elem = soup.select_one("h1.the-document-title")
            document_title = title_elem.text.strip() if title_elem else None
            
            links = []
            
            # Helper function to add link with title
            def add_link(href):
                full_url = urljoin(url, href)
                links.append({
                    'url': full_url,
                    'title': document_title if document_title else os.path.basename(href)
                })
            
            # First try finding links in the document entry section
            download_section = soup.find('div', class_='the-document-entry')
            if download_section:
                debug_log("Found document entry container")
                
                vn_doc = download_section.find('div', class_='vn-doc')
                if vn_doc:
                    debug_log("Found Vietnamese document section")
                    for a in vn_doc.find_all('a', href=True):
                        href = a.get('href')
                        if href and ('.doc' in href.lower() or '.pdf' in href.lower()):
                            add_link(href)
                            debug_log(f"Added document link: {href}")
            
            # Check list-download divs if no links found yet
            if not links:
                debug_log("Checking list-download divs")
                list_downloads = soup.find_all('div', class_='list-download')
                for list_download in list_downloads:
                    for a in list_download.find_all('a', href=True):
                        href = a.get('href')
                        if href and ('.doc' in href.lower() or '.pdf' in href.lower()):
                            add_link(href)
                            debug_log(f"Added document link: {href}")
            
            # If still no links, try finding any download links in the page
            if not links:
                debug_log("Searching for any download links")
                for a in soup.find_all('a', href=True):
                    href = a.get('href')
                    if href and ('.doc' in href.lower() or '.pdf' in href.lower()):
                        add_link(href)
                        debug_log(f"Added document link: {href}")
                        
            if links:
                debug_log(f"Found {len(links)} document links")
            else:
                debug_log("No document links found")
                
            return links
            
        except Exception as e:
            logger.exception(f"Error processing {url}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return []

def remove_duplicate_documents(download_folder="downloads"):
    """Remove PDF files when DOC/DOCX versions exist for the same document"""
    logger = setup_logger()
    duplicates_found = 0
    space_saved = 0
    
    def get_base_name(filename):
        """Get base name without extension and document ID"""
        # Remove extension
        base = os.path.splitext(filename)[0]
        # Remove document ID (typically last 6 digits)
        return re.sub(r'_?\d{6}$', '', base)
    
    def group_documents():
        """Group documents by their base names"""
        document_groups = {}
        
        # Walk through all files in download folder
        for root, _, files in os.walk(download_folder):
            for filename in files:
                if not filename.endswith(('.pdf', '.doc', '.docx')):
                    continue
                    
                base_name = get_base_name(filename)
                full_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                
                if base_name not in document_groups:
                    document_groups[base_name] = {'doc': [], 'pdf': []}
                
                if ext in ('.doc', '.docx'):
                    document_groups[base_name]['doc'].append(full_path)
                elif ext == '.pdf':
                    document_groups[base_name]['pdf'].append(full_path)
        
        return document_groups
    
    try:
        document_groups = group_documents()
        
        # Process each group
        for base_name, group in document_groups.items():
            # If we have both DOC and PDF versions
            if group['doc'] and group['pdf']:
                for pdf_path in group['pdf']:
                    try:
                        file_size = os.path.getsize(pdf_path)
                        os.remove(pdf_path)
                        duplicates_found += 1
                        space_saved += file_size
                        logger.info(f"Removed duplicate PDF: {pdf_path}")
                    except Exception as e:
                        logger.error(f"Error removing {pdf_path}: {str(e)}")
        
        # Print summary
        if duplicates_found > 0:
            mb_saved = space_saved / (1024 * 1024)  # Convert to MB
            print(f"\nDuplicate Removal Summary:")
            print(f"- Found and removed {duplicates_found} duplicate PDF files")
            print(f"- Saved approximately {mb_saved:.2f} MB of space")
        else:
            print("\nNo duplicate documents found")
            
        return duplicates_found, space_saved
        
    except Exception as e:
        logger.error(f"Error during duplicate removal: {str(e)}")
        return 0, 0

def process_document(url, session=None, debug=False):
    """Process single document download"""
    logger = setup_logger(debug)
    links = find_document_links(url, debug=debug, session=session)
    print(f"\nProcessing document: {url}")
    if not links:
        logger.info(f"No download links found for {url}")
        return False
        
    for link_info in links:
        doc_url = link_info['url']
        
        # Always use the title if available, otherwise format the filename
        if link_info.get('title'):
            filename = format_document_name(link_info['title'])
            logger.debug(f"Using formatted title: {filename}")
        else:
            filename = format_document_name(os.path.basename(doc_url))
            logger.debug(f"Using formatted URL basename: {filename}")
        
        success, error = download_file(doc_url, filename, "downloads")
        if success:
            logger.info(f"Successfully downloaded: {filename}")
        else:
            logger.error(f"Failed to download: {error}")
            
    return True