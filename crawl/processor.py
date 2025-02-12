import os
import psutil
import time
import pandas as pd
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from utils.common import setup_logger, DownloadStats
from crawl.downloader import (
    download_files_parallel,
    find_document_links,
    download_file,  # Ensure this import is present
)
from tqdm import tqdm
from utils.document_formatter import format_document_name
from crawl.progress_tracker import ProgressTracker  # Add this import


class TabManager:
    def __init__(self, session, max_tabs=3):
        self.session = session
        self.max_tabs = max_tabs
        self.active_tabs = []

    def create_tab(self):
        """Create a new browser tab"""
        self.session.driver.execute_script("window.open('');")
        new_window = self.session.driver.window_handles[-1]
        self.active_tabs.append(new_window)
        return new_window

    def get_available_tab(self):
        """Get or create an available tab"""
        while len(self.active_tabs) < self.max_tabs:
            return self.create_tab()
        return self.active_tabs[len(self.active_tabs) % self.max_tabs]

    def switch_to_tab(self, tab_handle):
        """Switch to specific tab"""
        self.session.driver.switch_to.window(tab_handle)

    def cleanup(self):
        """Close all tabs except the first one"""
        main_window = self.session.driver.window_handles[0]
        for handle in self.session.driver.window_handles[1:]:
            self.session.driver.switch_to.window(handle)
            self.session.driver.close()
        self.session.driver.switch_to.window(main_window)
        self.active_tabs = []


def get_optimal_workers():
    """Calculate optimal number of download workers based on system resources"""
    try:
        cpu_count = os.cpu_count() or 2
        memory = psutil.virtual_memory()
        # Use 75% of CPU cores, minimum 2, maximum 8
        cpu_optimal = max(2, min(8, int(cpu_count * 0.75)))
        # Reduce workers if memory usage is high (>80%)
        if memory.percent > 80:
            return max(2, cpu_optimal - 2)
        return cpu_optimal
    except Exception:
        return 4  # Default fallback


def get_user_workers():
    """Get number of workers from user input"""
    print("\nWorker Configuration:")
    print("1. Auto-detect optimal workers")
    print("2. Manually specify workers")
    choice = input("Enter choice (1/2): ").strip()

    if choice == "1":
        optimal = get_optimal_workers()
        print(f"\nDetected optimal workers: {optimal}")
        return optimal
    else:
        while True:
            try:
                workers = int(input("\nEnter number of workers (2-8 recommended): "))
                if workers > 12:
                    print("Warning: High number of workers may cause issues!")
                    confirm = input("Continue anyway? (y/n): ").lower()
                    if confirm != "y":
                        continue
                if workers > 0:
                    return workers
            except ValueError:
                print("Please enter a valid number")


class BatchProcessor:
    def __init__(self, batch_size=5, max_workers=None, max_tabs=3):
        self.batch_size = batch_size
        self.max_workers = max_workers or get_optimal_workers()
        self.max_tabs = max_tabs  # Number of browser tabs to use

    def process_batches(self, items):
        """Process items in batches, handling both lists and generators"""
        batch = []
        for item in items:
            batch.append(item)
            if len(batch) >= self.batch_size:
                yield batch
                batch = []
        if batch:
            yield batch


class BatchSettings:
    """Class to manage batch processing settings"""

    def __init__(self):
        self.max_workers = 4
        self.batch_size = 5
        self.max_tabs = 3
        self.chunk_size = 50
        self.retry_mode = False

    def customize(self):
        """Interactive settings customization"""
        print("\nBatch Processing Settings")
        print("========================")
        while True:
            print("\nCurrent Settings:")
            print(f"1. Workers per tab: {self.max_workers}")
            print(f"2. Batch size: {self.batch_size}")
            print(f"3. Parallel tabs: {self.max_tabs}")
            print(f"4. Chunk size: {self.chunk_size}")
            print(f"5. Retry mode: {self.retry_mode}")
            print("6. Save and continue")
            print("7. Reset to defaults")

            choice = input("\nEnter choice (1-7): ").strip()

            if choice == "1":
                try:
                    workers = int(input("\nEnter workers per tab (2-8 recommended): "))
                    if 1 <= workers <= 12:
                        self.max_workers = workers
                    else:
                        print("Invalid value. Using previous setting.")
                except ValueError:
                    print("Invalid input. Using previous setting.")

            elif choice == "2":
                try:
                    size = int(input("\nEnter batch size (5-20 recommended): "))
                    if 1 <= size <= 50:
                        self.batch_size = size
                    else:
                        print("Invalid value. Using previous setting.")
                except ValueError:
                    print("Invalid input. Using previous setting.")

            elif choice == "3":
                try:
                    tabs = int(
                        input("\nEnter number of parallel tabs (2-5 recommended): ")
                    )
                    if 1 <= tabs <= 8:
                        self.max_tabs = tabs
                    else:
                        print("Invalid value. Using previous setting.")
                except ValueError:
                    print("Invalid input. Using previous setting.")

            elif choice == "4":
                try:
                    chunk = int(input("\nEnter chunk size (50-200 recommended): "))
                    if 10 <= chunk <= 500:
                        self.chunk_size = chunk
                    else:
                        print("Invalid value. Using previous setting.")
                except ValueError:
                    print("Invalid input. Using previous setting.")

            elif choice == "5":
                retry = input("\nEnable retry mode? (y/n): ").lower()
                self.retry_mode = retry == "y"

            elif choice == "6":
                return True

            elif choice == "7":
                self.__init__()  # Reset to defaults
                print("\nSettings reset to defaults")

            else:
                print("\nInvalid choice!")


def process_batch_file(file_path, session=None, debug=False, resume=True):
    """Process a batch file containing URLs to download"""
    logger = setup_logger(debug)

    # Create settings instance and tab manager
    settings = BatchSettings()
    tab_manager = TabManager(session, max_tabs=settings.max_tabs)

    # Create and initialize tracker
    tracker = ProgressTracker(file_path) if resume else None

    try:
        df = pd.read_excel(file_path)
        if "Url" not in df.columns:
            logger.error("Excel file must contain a 'Url' column")
            return False

        total_rows = len(df)
        processed = 0
        print(f"\nProcessing {total_rows} URLs from {os.path.basename(file_path)}")

        with tqdm(total=total_rows, desc="Processing URLs") as pbar:
            if resume and tracker:
                processed_urls = tracker.get_processed_urls()
                processed = len(processed_urls)
                pbar.update(processed)

                # Filter out already processed URLs
                df = df[~df["Url"].isin(processed_urls)]

            # Process URLs using multiple tabs
            for chunk_start in range(0, len(df), settings.batch_size):
                chunk = df.iloc[chunk_start : chunk_start + settings.batch_size]

                # Process chunk URLs in parallel using available tabs
                for _, row in chunk.iterrows():
                    url = row["Url"]
                    if pd.isna(url):
                        continue

                    # Get available tab and process URL
                    tab = tab_manager.get_available_tab()
                    tab_manager.switch_to_tab(tab)

                    try:
                        if process_document(url, session=session, debug=debug):
                            if tracker:
                                tracker.mark_success(url)
                            processed += 1
                            pbar.set_description(f"Success: {url}")
                        else:
                            if tracker:
                                tracker.mark_failure(url, "Download failed")
                            pbar.set_description(f"Failed: {url}")
                    except Exception as e:
                        if tracker:
                            tracker.mark_failure(url, str(e))
                        logger.error(f"Error processing {url}: {str(e)}")

                    pbar.update(1)

                # Brief delay between chunks
                time.sleep(0.5)

        print(f"\nCompleted batch processing: {processed}/{total_rows} successful")
        return True

    except Exception as e:
        logger.error(f"Error processing batch file {file_path}: {str(e)}")
        return False

    finally:
        # Cleanup tabs when done
        tab_manager.cleanup()


def process_chunk_with_tab(chunk_df, session, progress_data, config):
    """Process a chunk of URLs in a separate browser tab"""
    logger = setup_logger(config.get("debug", False))
    chunk_progress = {}

    try:
        # Create a new tab in the browser
        session.driver.execute_script("window.open('');")
        new_window = session.driver.window_handles[-1]
        session.driver.switch_to.window(new_window)

        for index, row in chunk_df.iterrows():
            if str(index) in progress_data and progress_data[str(index)]["success"]:
                continue

            url = row["Url"]
            if pd.isna(url):
                continue

            try:
                doc_links = find_document_links(
                    url, debug=config["debug"], session=session
                )
                if doc_links:
                    # Process downloads
                    success = process_url_downloads(url, doc_links, row, config)
                    chunk_progress[str(index)] = {
                        "url": url,
                        "success": success,
                        "timestamp": datetime.now().isoformat(),
                    }
            except Exception as e:
                if config["debug"]:
                    logger.error(f"Error processing {url}: {str(e)}")
                chunk_progress[str(index)] = {
                    "url": url,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }

        # Close the tab when done
        session.driver.close()
        session.driver.switch_to.window(session.driver.window_handles[0])

        return chunk_progress

    except Exception as e:
        logger.exception(f"Error in process_chunk_with_tab: {str(e)}")
        # Make sure to switch back to main window
        if len(session.driver.window_handles) > 1:
            session.driver.close()
            session.driver.switch_to.window(session.driver.window_handles[0])
        return chunk_progress


def process_url_downloads(url, doc_links, row, config):
    """Process downloads for a single URL"""
    logger = setup_logger(config.get("debug", False))
    try:
        base_filename = format_document_name(url)
        success = False

        for doc_link in doc_links:
            filename = (
                f"{base_filename}.{'docx' if doc_link['type'] == 'doc' else 'pdf'}"
            )
            field = str(row.get("Lĩnh vực", "unknown")).strip()
            year = str(pd.to_datetime(row.get("Ban hành", pd.Timestamp.now())).year)
            folder = os.path.join("downloads", field, year)

            download_success, _ = download_file(
                doc_link["url"], filename, folder, retry_mode=config["retry_mode"]
            )
            success = success or download_success

        return success

    except Exception as e:
        logger.error(f"Error downloading from {url}: {str(e)}")
        return False


def process_url_chunk(args):
    """Process a chunk of URLs in a separate process"""
    urls, fields, years, session_args, config = args
    logger = setup_logger(session_args.get("debug", False))
    results = []
    downloads = []

    try:
        for url, field_list, year in zip(urls, fields, years):
            try:
                # Get document links using session
                doc_links = find_document_links(
                    url,
                    debug=session_args.get("debug", False),
                    session=session_args.get("session"),
                )
                if doc_links:
                    download_tasks = []
                    # Extract base filename from the URL first
                    base_filename = format_document_name(url)

                    for doc_link in doc_links:
                        # Use base filename + appropriate extension
                        if doc_link["type"] == "doc":
                            filename = f"{base_filename}.docx"
                        else:
                            filename = f"{base_filename}.pdf"

                        for field in field_list:
                            folder = os.path.join("downloads", str(field), year)
                            download_tasks.append((doc_link["url"], filename, folder))

                    if download_tasks:
                        success, status = download_files_parallel(
                            *zip(*download_tasks),
                            max_workers=config.get("max_workers", 4),
                            retry_mode=config.get("retry_mode", False),
                        )
                        results.append(any(success))
                        downloads.append(status.get_summary())
                        continue

                results.append(False)
                downloads.append(None)

            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
                results.append(False)
                downloads.append(None)

        return results, downloads

    except Exception:
        logger.exception("Error in process_url_chunk")
        return [False] * len(urls), [None] * len(urls)


def process_excel_file(args):
    """Process a single Excel file with parallel processing"""
    file_path, session_args, config = args
    logger = setup_logger(config.get("debug", False))
    stats = DownloadStats()

    try:
        df = pd.read_excel(file_path)

        # Fill missing values
        df["Lĩnh vực"] = df["Lĩnh vực"].fillna("unknown")
        df["Ban hành"] = pd.to_datetime(
            df["Ban hành"], format="%d/%m/%Y", dayfirst=True, errors="coerce"
        )
        df["Ban hành"] = df["Ban hành"].fillna(pd.Timestamp.now())

        chunk_size = config.get("chunk_size", 50)
        chunks = []

        # Create chunks
        for i in range(0, len(df), chunk_size):
            chunk_df = df.iloc[i : i + chunk_size]
            chunks.append(
                (
                    chunk_df["Url"].tolist(),
                    [field.split(";") for field in chunk_df["Lĩnh vực"]],
                    [str(date.year) for date in chunk_df["Ban hành"]],
                )
            )

        # Process chunks
        completed = 0
        with ProcessPoolExecutor(
            max_workers=config.get("max_processes", 4)
        ) as executor:
            futures = [
                executor.submit(
                    process_url_chunk,
                    (chunk[0], chunk[1], chunk[2], session_args, config),
                )
                for chunk in chunks
            ]

            for future in futures:
                try:
                    results, download_stats = future.result()
                    completed += len([r for r in results if r])

                    # Update statistics from successful downloads
                    for stat in download_stats:
                        if stat:
                            for ext, count in stat.items():
                                if ext != "total":
                                    stats.add_success(ext)

                except Exception as e:
                    logger.error(f"Error processing chunk: {str(e)}")

        return stats, completed

    except Exception:
        logger.exception(f"Error processing excel file {file_path}")
        return DownloadStats(), 0


def process_document(url, session=None, debug=False):
    """Process single document download"""
    logger = setup_logger(debug)
    links = find_document_links(url, debug=debug, session=session)
    print(f"\nProcessing document: {url}")
    if not links:
        logger.info(f"No download links found for {url}")
        return False

    for link_info in links:
        doc_url = link_info["url"]

        filename = format_document_name(link_info["title"])
        logger.debug(f"Using formatted title: {filename}")

        success, error = download_file(doc_url, filename, "downloads")
        if success:
            logger.info(f"Successfully downloaded: {filename}")
        else:
            logger.error(f"Failed to download: {error}")

    return True
