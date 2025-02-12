"""
Document downloading and link extraction module.
Features:
- Thread-safe file downloading
- Parallel download management
- Document link detection
- Duplicate file handling
- File locking mechanisms
"""

import os
import requests
import atexit
import time
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor  # Add this import
from utils.common import setup_logger, DownloadStats
from utils.document_formatter import format_document_name  # Remove format_title import
import re  # Add this import if not already present
from lxml import html  # Add this import
import urllib3

# Suppress SSL warnings globally since we're dealing with a known host
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

active_locks = set()


def cleanup_locks():
    """Clean up any remaining lock files"""
    for lock_file in active_locks:
        try:
            if os.path.exists(lock_file):
                os.unlink(lock_file)
        except:
            pass  # Ignore errors during cleanup


# Register cleanup function
atexit.register(cleanup_locks)


def download_file(url, filename, folder="downloads", retry_mode=False, title=None):
    """Enhanced download with connection pooling and chunked transfer"""
    logger = setup_logger()

    try:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        filepath = os.path.join(folder, filename)

        # Use session with keep-alive and optimized settings
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )

        if "static.luatvietnam.vn" in url:
            session.verify = False

        # Use stream mode with larger chunk size
        response = session.get(url, stream=True, timeout=(5, 30))

        if response.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(
                    chunk_size=16384
                ):  # Increased chunk size
                    if chunk:
                        f.write(chunk)
            return True, None
        else:
            logger.error(
                f"Download failed with status {response.status_code} for {url}"
            )
            return False, f"HTTP {response.status_code}"

    except Exception as e:
        logger.error(f"Error downloading {url}: {str(e)}")
        return False, str(e)
    finally:
        if "session" in locals():
            session.close()


def _do_download(url, filepath):
    """Process-safe download implementation"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        response = requests.get(url, headers=headers, stream=True)

        if response.status_code == 200:
            # Download directly to final location
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                f.flush()
                os.fsync(f.fileno())  # Ensure all data is written

            return True, None

        return False, f"HTTP {response.status_code}"

    except Exception as e:
        return False, str(e)


def download_files_parallel(
    urls, filenames, folders, max_workers=None, batch_size=5, retry_mode=False
):
    """Optimized parallel download handling"""
    logger = setup_logger()
    status = DownloadStats()

    if not max_workers:
        max_workers = min(len(urls), 8)  # Increased default max workers

    # Group downloads by domain to reuse connections
    domain_groups = {}
    for url, filename, folder in zip(urls, filenames, folders):
        domain = url.split("/")[2]
        if domain not in domain_groups:
            domain_groups[domain] = []
        domain_groups[domain].append((url, filename, folder))

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Process each domain group
        for domain_tasks in domain_groups.values():
            futures = []
            for i in range(0, len(domain_tasks), batch_size):
                batch = domain_tasks[i : min(i + batch_size, len(domain_tasks))]
                futures.extend(
                    [
                        executor.submit(
                            download_worker, (url, filename, folder, retry_mode)
                        )
                        for url, filename, folder in batch
                    ]
                )

            # Small delay between batches for same domain
            time.sleep(0.2)

            for future in futures:
                try:
                    url, filename, folder, success, error = future.result()
                    filepath = os.path.join(folder, filename)
                    status.add_download(url, filepath, success, error)
                    results.append(success)
                except Exception as e:
                    logger.error(f"Download worker error: {str(e)}")
                    results.append(False)

    return results, status


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
        return re.sub(r"_?\d{6}$", "", base)

    def get_document_groups():
        """Group documents by their base names"""
        document_groups = {}

        for root, _, files in os.walk(download_folder):
            for filename in files:
                if not filename.lower().endswith((".pdf", ".doc", ".docx")):
                    continue

                base_name = get_base_name(filename)
                full_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()

                if base_name not in document_groups:
                    document_groups[base_name] = {"doc": [], "pdf": []}

                if ext in (".doc", ".docx"):
                    document_groups[base_name]["doc"].append(full_path)
                elif ext == ".pdf":
                    document_groups[base_name]["pdf"].append(full_path)

        return document_groups

    try:
        document_groups = get_document_groups()

        # Process each group
        for base_name, group in document_groups.items():
            # If we have both DOC and PDF versions
            if group["doc"] and group["pdf"]:
                for pdf_path in group["pdf"]:
                    try:
                        # Get file size before removal
                        file_size = os.path.getsize(pdf_path)
                        space_saved += file_size

                        # Remove the PDF file
                        os.remove(pdf_path)
                        duplicates_found += 1
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


def find_document_links(url, debug=False, session=None):
    """Find document download links in a page"""
    logger = setup_logger(debug)
    if not session:
        logger.error("No session provided")
        return []

    # Use session's browser-based method
    return session.find_document_links(url, debug)


def download_worker(task):
    """Worker function for parallel downloads"""
    url, filename, folder, retry_mode = task
    try:
        success, error = download_file(url, filename, folder, retry_mode)
        return url, filename, folder, success, error
    except Exception as e:
        return url, filename, folder, False, str(e)


def extract_download_links(soup, base_url, debug=False):
    """Extract download links from page content"""
    logger = setup_logger(debug)
    links = []

    # Look for download links using multiple patterns
    patterns = [
        ".//a[contains(@href, 'VIETLAWFILE')]",
        ".//a[contains(@href, 'static.luatvietnam.vn')]",
        ".//a[contains(@title, 'Bản Word') or contains(@title, 'PDF')]",
        ".//a[contains(text(), 'DOC') or contains(text(), 'PDF')]",
    ]

    try:
        tree = html.fromstring(str(soup))
        for pattern in patterns:
            elements = tree.xpath(pattern)
            for elem in elements:
                href = elem.get("href")
                if href and any(
                    ext in href.lower() for ext in [".doc", ".docx", ".pdf"]
                ):
                    # Determine file type
                    file_type = "pdf" if ".pdf" in href.lower() else "doc"
                    full_url = urljoin(base_url, href)

                    # Skip if already found
                    if not any(link["url"] == full_url for link in links):
                        links.append(
                            {
                                "url": full_url,
                                "type": file_type,
                                "text": elem.text_content().strip()
                                if elem.text
                                else "",
                            }
                        )
                        if debug:
                            logger.debug(f"Found {file_type.upper()} link: {href}")

    except Exception as e:
        if debug:
            logger.error(f"Error extracting links: {str(e)}")

    return links


def verify_download_url(url, session=None):
    """Verify if download URL is valid"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        if session:
            response = session.session.head(url, allow_redirects=True)
        else:
            response = requests.head(url, headers=headers, allow_redirects=True)

        return response.status_code == 200

    except Exception:
        return False


def clean_filename(filename):
    """Clean filename of invalid characters"""
    # Remove or replace invalid filename characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # Ensure filename isn't too long
    max_length = 240  # Leave room for path
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[: max_length - len(ext)] + ext

    return filename.strip()


def ensure_download_folder(folder):
    """Ensure download folder exists and is writable"""
    try:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        # Verify we can write to folder
        test_file = os.path.join(folder, ".write_test")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.unlink(test_file)
            return True
        except Exception:
            return False

    except Exception:
        return False
