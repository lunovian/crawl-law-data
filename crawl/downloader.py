import os
import requests
import portalocker
import atexit
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from utils.common import setup_logger, DownloadStats
from utils.document_formatter import format_document_name
import re
from lxml import html
import aiohttp
import asyncio
import aiofiles
from typing import List, Dict, Tuple
from dataclasses import dataclass
from tqdm.asyncio import tqdm_asyncio

active_locks = set()


def cleanup_locks():
    """Clean up any remaining lock files"""
    for lock_file in active_locks:
        try:
            if os.path.exists(lock_file):
                os.unlink(lock_file)
        except OSError:
            pass


# Register cleanup function
atexit.register(cleanup_locks)


def download_file(url, filename, folder="downloads", retry_mode=False, title=None):
    """Thread-safe and process-safe file download with robust locking"""
    # Get extension from URL
    ext = os.path.splitext(url)[1].lower()
    if not ext:
        ext = ".pdf" if ".pdf" in url.lower() else ".doc"

    # Format the filename and add proper extension
    formatted_filename = format_document_name(filename)
    final_filename = f"{formatted_filename}{ext}"

    # Create lock file path
    lock_file = os.path.join(folder, f"{final_filename}.lock")

    try:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        filepath = os.path.join(folder, final_filename)

        # Skip locking in retry mode
        if retry_mode:
            return _do_download(url, filepath)

        # Use portalocker for cross-process locking
        with portalocker.Lock(lock_file, timeout=60):
            if os.path.exists(filepath):  # Check again after acquiring lock
                return True, None

            result = _do_download(url, filepath)
            return result

    except portalocker.exceptions.LockException:
        # If we timeout waiting for lock, skip this file
        return False, "File locked by another process"
    except Exception as e:
        return False, str(e)
    finally:
        try:
            if os.path.exists(lock_file):
                os.unlink(lock_file)
        except OSError:
            pass


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
    """Enhanced parallel download using FastDownloader"""

    async def run_downloads():
        downloader = FastDownloader(concurrent_limit=max_workers or 8)

        # Create download tasks
        tasks = [
            DownloadTask(url=url, filename=fname, folder=folder)
            for url, fname, folder in zip(urls, filenames, folders)
        ]

        # Process in batches
        results = []
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            batch_results = await downloader.process_batch(batch)
            results.extend(batch_results)

        await downloader.close()
        return results

    # Run async downloads
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(run_downloads())
    finally:
        loop.close()

    # Process results
    status = DownloadStats()
    for (url, filename, folder), (success, error) in zip(
        zip(urls, filenames, folders), results
    ):
        filepath = os.path.join(folder, filename)
        status.add_download(url, filepath, success=success, error=error)

    return [r[0] for r in results], status


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
            print("\nDuplicate Removal Summary:")
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


def format_title(title):
    """Format document title into a valid filename"""
    if not title:
        return None

    # Remove invalid characters
    title = re.sub(r'[<>:"/\\|?*]', "_", title)

    # Remove multiple spaces and underscores
    title = re.sub(r"[\s_]+", "_", title)

    # Remove leading/trailing underscores
    title = title.strip("_")

    # Ensure it's not too long (leave room for extension)
    if len(title) > 240:
        title = title[:240]

    return title if title else None


@dataclass
class DownloadTask:
    url: str
    filename: str
    folder: str
    file_type: str = None
    retry_count: int = 0


class FastDownloader:
    def __init__(self, concurrent_limit=10, chunk_size=8192):
        self.concurrent_limit = concurrent_limit
        self.chunk_size = chunk_size
        self.session = None
        self.logger = setup_logger()
        self.download_semaphore = asyncio.Semaphore(concurrent_limit)
        self.progress_bars = {}

    async def init_session(self):
        """Initialize optimized aiohttp session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            connector = aiohttp.TCPConnector(
                limit=self.concurrent_limit,
                force_close=False,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                },
            )

    async def download_file_async(self, task: DownloadTask) -> Tuple[bool, str]:
        """Download single file asynchronously with progress bar"""
        async with self.download_semaphore:
            try:
                filepath = os.path.join(task.folder, task.filename)

                # Create folder if doesn't exist
                os.makedirs(task.folder, exist_ok=True)

                async with self.session.get(task.url) as response:
                    if response.status != 200:
                        return False, f"HTTP {response.status}"

                    total_size = int(response.headers.get("content-length", 0))

                    # Create progress bar
                    pbar = tqdm_asyncio(
                        total=total_size, unit="B", unit_scale=True, desc=task.filename
                    )

                    async with aiofiles.open(filepath, "wb") as f:
                        async for chunk in response.content.iter_chunked(
                            self.chunk_size
                        ):
                            await f.write(chunk)
                            pbar.update(len(chunk))

                    pbar.close()
                    return True, None

            except Exception as e:
                return False, str(e)

    async def process_batch(self, tasks: List[DownloadTask]) -> List[Tuple[bool, str]]:
        """Process multiple downloads concurrently"""
        await self.init_session()
        results = await asyncio.gather(
            *[self.download_file_async(task) for task in tasks]
        )
        return results

    def extract_links_bs4(self, html_content: str, base_url: str) -> List[Dict]:
        """Extract download links using BeautifulSoup"""
        soup = BeautifulSoup(html_content, "html.parser")
        links = []

        # Find all download links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(ext in href.lower() for ext in [".doc", ".docx", ".pdf"]):
                full_url = urljoin(base_url, href)
                file_type = "pdf" if ".pdf" in href.lower() else "doc"

                # Check if it's a valid download link
                if "download" in a.get("class", []) or "download" in href.lower():
                    links.append(
                        {
                            "url": full_url,
                            "type": file_type,
                            "text": a.get_text(strip=True),
                        }
                    )

        return links

    async def close(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
