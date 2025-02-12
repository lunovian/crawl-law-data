import os
import sys
import signal
import argparse

from tqdm import tqdm
from utils.session import LawVNSession
from crawl.processor import process_document, process_batch_file
from crawl.downloader import remove_duplicate_documents
import json
from crawl.progress_tracker import ProgressTracker
from crawl.batch_config import BatchConfig
import threading
import itertools
import time


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Law Document Crawler")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Disable headless mode (show browser)",
    )
    return parser.parse_args()


def check_login():
    """Check if login is valid"""
    try:
        if not os.path.exists("lawvn_cookies.pkl"):
            print("\nNo login session found.")
            return False

        session = LawVNSession(debug=True)
        is_valid = session.check_login()

        if session.debug:
            print(f"\nDebug: Session valid: {is_valid}")
            print(f"Debug: Active cookies: {session.get_cookies()}")

        return is_valid

    except Exception as e:
        print(f"\nError checking login: {e}")
        return False


def setup_config():
    """Setup or update config.json file"""
    config_file = "config.json"
    config = {}

    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    print("\nGoogle Account Setup")
    print("-------------------")
    print("Enter your Google account credentials:")
    email = input("Email: ").strip()
    password = input("Password: ").strip()

    config["google_credentials"] = {"email": email, "password": password}

    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)
        print("\n✓ Credentials saved to config.json")
        return True
    except Exception as e:
        print(f"\n✗ Error saving config: {e}")
        return False


def menu_login(debug=False, headless=True):
    """Handle login process"""
    print("\nLogin Options:")
    print("1. Use saved credentials")
    print("2. Setup/update credentials")
    print("3. Back")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice == "1":
        if os.path.exists("config.json"):
            print("\nAttempting login...")

            # First try with saved cookies in headless mode
            if os.path.exists("lawvn_cookies.pkl"):
                print("Found saved cookies, attempting to use them...")
                session = LawVNSession(debug=debug, headless=headless)
                session.load_cookies()
                if session.check_login():
                    print("\n✓ Login successful with saved cookies!")
                    return session
                print("Saved cookies are invalid, trying with credentials...")

            # If cookies failed or don't exist, try normal login
            session = LawVNSession(debug=debug, headless=False)
            if session.login(force=True):
                print("\n✓ Login successful!")
                # Save cookies for future use
                session.save_cookies()

                # Create new session with desired headless setting
                if headless:
                    new_session = LawVNSession(debug=debug, headless=True)
                    new_session.load_cookies()
                    return new_session
                return session
            else:
                print("\n✗ Login failed with saved credentials.")
                if (
                    input("Would you like to update credentials? (y/n): ").lower()
                    == "y"
                ):
                    setup_config()

    elif choice == "2":
        setup_config()
        if input("\nWould you like to try logging in now? (y/n): ").lower() == "y":
            session = LawVNSession(debug=debug, headless=False)
            if session.login(force=True):
                print("\n✓ Login successful!")
                # Save cookies for future use
                session.save_cookies()

                # Create new session with desired headless setting
                if headless:
                    new_session = LawVNSession(debug=debug, headless=True)
                    new_session.load_cookies()
                    return new_session
                return session
            else:
                print("\n✗ Login failed. Please check your credentials.")

    return None


def menu_single_url(debug=False, headless=True, session=None):
    """Process single URL"""
    if not session or not session.check_login():
        print("Please login first!")
        return

    url = input("\nEnter URL to process: ").strip()
    if not url:
        return

    success = process_document(url, session=session, debug=debug)  # Pass debug flag

    if success:
        print("\nDocument processed successfully!")
    else:
        print("\nFailed to process document.")


def loading_animation(stop_event, message="Loading"):
    """Show a loading animation"""
    spinner = itertools.cycle(["-", "/", "|", "\\"])
    while not stop_event.is_set():
        sys.stdout.write(f"\r{message} {next(spinner)}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")
    sys.stdout.flush()


def menu_batch_process(debug=False, session=None):
    """Start batch processing"""
    if not session or not session.check_login():
        print("Please login first!")
        return

    # Show loading animation while checking files
    stop_loading = threading.Event()
    loading_thread = threading.Thread(
        target=loading_animation,
        args=(stop_loading, "Checking batch files and loading settings"),
    )
    loading_thread.start()

    try:
        # Initialize batch config and check files
        config = BatchConfig()
        config.load()

        # Simulate some loading time if needed
        time.sleep(1)  # Remove this in production

        clear_screen()
        print("\nBatch Processing Options:")
        print("1. Process all Excel files in 'batches' folder")
        print("2. Select specific Excel file")
        print("3. Configure batch settings")
        print("4. Show download progress")
        print("5. Retry failed downloads")
        print("6. Back")

        # Show current settings
        settings = config.get_settings()["download"]
        print("\nCurrent batch settings:")
        print(f"- Workers: {settings['max_workers']}")
        print(f"- Batch size: {settings['batch_size']}")
        print(f"- Retry mode: {settings['retry_mode']}")

        # Show batch files status
        if os.path.exists("batches"):
            excel_files = [
                f for f in os.listdir("batches") if f.endswith((".xlsx", ".xls"))
            ]
            print(f"\nFound {len(excel_files)} Excel files in batches folder")
        else:
            print("\nNo batches folder found")

    finally:
        # Stop loading animation
        stop_loading.set()
        loading_thread.join()

    choice = input("\nEnter choice (1-6): ").strip()

    if choice == "1":
        if not os.path.exists("batches"):
            print("\nNo 'batches' folder found. Creating one...")
            os.makedirs("batches")
            print("\nPlease add Excel files to the 'batches' folder and try again.")
            return

        excel_files = [
            f for f in os.listdir("batches") if f.endswith((".xlsx", ".xls"))
        ]
        if not excel_files:
            print("\nNo Excel files found in 'batches' folder.")
            return

        print(f"\nFound {len(excel_files)} Excel files.")
        for excel_file in excel_files:
            file_path = os.path.join("batches", excel_file)
            print(f"\nProcessing: {excel_file}")
            process_batch_file(file_path, session=session, debug=debug, resume=True)

    elif choice == "2":
        if not os.path.exists("batches"):
            print("\nNo 'batches' folder found. Creating one...")
            os.makedirs("batches")
            print("\nPlease add Excel files to the 'batches' folder and try again.")
            return

        excel_files = [
            f for f in os.listdir("batches") if f.endswith((".xlsx", ".xls"))
        ]
        if not excel_files:
            print("\nNo Excel files found in 'batches' folder.")
            return

        print("\nAvailable Excel files:")
        for i, file in enumerate(excel_files, 1):
            print(f"{i}. {file}")

        while True:
            try:
                file_num = int(input("\nEnter file number to process: "))
                if 1 <= file_num <= len(excel_files):
                    file_path = os.path.join("batches", excel_files[file_num - 1])
                    print(f"\nProcessing: {excel_files[file_num - 1]}")
                    process_batch_file(
                        file_path, session=session, debug=debug, resume=True
                    )
                    break
            except ValueError:
                print("Please enter a valid number")

    elif choice == "4":
        show_download_progress()

    elif choice == "5":
        retry_failed_downloads(session, debug)


def show_download_progress():
    """Show progress for all batch files with CSV support"""
    if not os.path.exists("batches"):
        print("\nNo batches folder found.")
        return

    excel_files = [f for f in os.listdir("batches") if f.endswith((".xlsx", ".xls"))]
    if not excel_files:
        print("\nNo Excel files found.")
        return

    # Show loading animation
    stop_loading = threading.Event()
    loading_thread = threading.Thread(
        target=loading_animation,
        args=(stop_loading, "Loading progress data"),
    )
    loading_thread.start()

    try:
        print("\nDownload Progress Summary:")
        print("------------------------")
        total_processed = 0
        total_failed = 0

        for file in excel_files:
            file_path = os.path.join("batches", file)
            tracker = ProgressTracker(file_path)

            processed = len(tracker.get_processed_urls())
            failed = len(tracker.get_failed_urls())
            total_processed += processed
            total_failed += failed

            # Get most recent timestamp
            failed_items = tracker.progress["failed"]
            latest_time = (
                max([item["timestamp"] for item in failed_items])
                if failed_items
                else "N/A"
            )

            print(f"\n{file}:")
            print(f"  ✓ Processed: {processed}")
            print(f"  ✗ Failed: {failed}")
            print(f"  Last update: {latest_time}")

            # Show error summary if there are failures
            if failed > 0:
                print("\n  Recent failures:")
                for item in failed_items[-3:]:  # Show last 3 failures
                    print(f"  - {item['url']}: {item['error']}")

        print("\nOverall Progress:")
        print(f"Total processed: {total_processed}")
        print(f"Total failed: {total_failed}")
        print(
            f"Success rate: {(total_processed / (total_processed + total_failed) * 100):.1f}%"
        )

    finally:
        stop_loading.set()
        loading_thread.join()

    input("\nPress Enter to continue...")


def retry_failed_downloads(session, debug=False):
    """Retry failed downloads from CSV progress files"""
    if not os.path.exists("batches"):
        print("\nNo batches folder found.")
        return

    excel_files = [f for f in os.listdir("batches") if f.endswith((".xlsx", ".xls"))]
    if not excel_files:
        print("\nNo Excel files found.")
        return

    # Show loading animation while gathering failed URLs
    stop_loading = threading.Event()
    loading_thread = threading.Thread(
        target=loading_animation,
        args=(stop_loading, "Gathering failed downloads"),
    )
    loading_thread.start()

    try:
        # Gather all failed downloads
        retry_queue = []
        for file in excel_files:
            file_path = os.path.join("batches", file)
            tracker = ProgressTracker(file_path)
            failed_urls = tracker.get_failed_urls()
            if failed_urls:
                retry_queue.extend([(url, tracker) for url in failed_urls])

        stop_loading.set()
        loading_thread.join()

        if not retry_queue:
            print("\nNo failed downloads found.")
            return

        print(f"\nFound {len(retry_queue)} failed downloads")
        print("1. Retry all")
        print("2. Select specific files")
        print("3. Back")

        choice = input("\nEnter choice (1-3): ").strip()

        if choice == "1":
            with tqdm(total=len(retry_queue), desc="Retrying downloads") as pbar:
                for url, tracker in retry_queue:
                    if process_document(url, session=session, debug=debug):
                        tracker.mark_success(url)
                        pbar.set_description(f"Success: {url}")
                    else:
                        tracker.mark_failure(url, "Retry failed")
                        pbar.set_description(f"Failed: {url}")
                    pbar.update(1)
                    time.sleep(0.5)  # Brief delay between retries

        elif choice == "2":
            print("\nFailed downloads by file:")
            file_groups = {}
            for file in excel_files:
                path = os.path.join("batches", file)
                tracker = ProgressTracker(path)
                failed = tracker.get_failed_urls()
                if failed:
                    file_groups[file] = (failed, tracker)

            for i, (file, (failed, _)) in enumerate(file_groups.items(), 1):
                print(f"{i}. {file} ({len(failed)} failed)")

            try:
                file_num = int(input("\nSelect file to retry (number): "))
                if 1 <= file_num <= len(file_groups):
                    selected_file = list(file_groups.keys())[file_num - 1]
                    failed_urls, tracker = file_groups[selected_file]

                    print(f"\nRetrying downloads for {selected_file}")
                    with tqdm(total=len(failed_urls), desc="Retrying") as pbar:
                        for url in failed_urls:
                            if process_document(url, session=session, debug=debug):
                                tracker.mark_success(url)
                                pbar.set_description(f"Success: {url}")
                            else:
                                tracker.mark_failure(url, "Retry failed")
                                pbar.set_description(f"Failed: {url}")
                            pbar.update(1)
                            time.sleep(0.5)
            except ValueError:
                print("Invalid selection")

    finally:
        if not stop_loading.is_set():
            stop_loading.set()
            loading_thread.join()

    input("\nPress Enter to continue...")


def menu_cleanup():
    """Run cleanup operations"""
    print("\nCleanup Options:")
    print("1. Remove duplicate PDFs")
    print("2. Remove lock files")
    print("3. Back")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice == "1":
        print("\nChecking for duplicate PDFs...")
        duplicates, space_saved = remove_duplicate_documents()
        if duplicates > 0:
            mb_saved = space_saved / (1024 * 1024)
            print(f"\nRemoved {duplicates} duplicate files")
            print(f"Saved {mb_saved:.2f} MB of space")
        else:
            print("\nNo duplicates found")

    elif choice == "2":
        count = 0
        for root, _, files in os.walk("downloads"):
            for file in files:
                if file.endswith(".lock"):
                    try:
                        os.unlink(os.path.join(root, file))
                        count += 1
                    except OSError:
                        pass
        print(f"\nRemoved {count} lock files")


def cleanup_and_exit(monitor_process=None):  # We can simplify this function
    """Clean shutdown of all processes"""
    print("\nShutting down gracefully...")

    # Clean any lock files
    for root, _, files in os.walk("downloads"):
        for f in files:
            if f.endswith(".lock"):
                try:
                    os.unlink(os.path.join(root, f))
                except OSError:
                    pass

    os._exit(0)


def signal_handler(signum, frame):
    """Handle interruption signals"""
    cleanup_and_exit()


def menu_batch_settings():
    """Configure batch processing settings"""
    config = BatchConfig()

    while True:
        clear_screen()
        print("\nBatch Configuration Options:")
        print("1. Show current settings")
        print("2. Configure settings")
        print("3. Auto-configure based on system")
        print("4. Reset to defaults")
        print("5. Back")

        choice = input("\nEnter choice (1-5): ").strip()

        if choice == "1":
            clear_screen()
            settings = config.get_settings()
            print("\nCurrent Settings:")
            for section, values in settings.items():
                print(f"\n{section.title()}:")
                for key, value in values.items():
                    print(f"- {key}: {value}")
            print(f"\nSettings file: {config.config_file}")
            input("\nPress Enter to continue...")

        elif choice == "2":
            clear_screen()
            config.configure_interactive()
            if config.save():
                print("\n✓ Settings saved successfully")
            else:
                print("\n✗ Failed to save settings")
            input("\nPress Enter to continue...")

        elif choice == "3":
            clear_screen()
            from crawl.processor import get_auto_batch_settings

            auto_settings = get_auto_batch_settings()
            config.settings["download"].update(auto_settings)
            success = config.save()

            print("\nSettings automatically configured based on system resources:")
            for key, value in auto_settings.items():
                print(f"- {key}: {value}")

            if success:
                print("\n✓ Settings saved successfully")
            else:
                print("\n✗ Failed to save settings")

            confirm = input("\nKeep these settings? (y/n): ").lower()
            if confirm != "y":
                config.load_defaults()
                config.save()
                print("\nReverted to default settings")
            input("\nPress Enter to continue...")

        elif choice == "4":
            clear_screen()
            config.load_defaults()
            if config.save():
                print("\n✓ Settings reset to defaults successfully")
            else:
                print("\n✗ Failed to reset settings")
            input("\nPress Enter to continue...")

        elif choice == "5":
            print("Returning to main menu...")
            return  # Exit the menu


def main_menu(debug=False, headless=True):
    """Display and handle main menu"""
    session = None
    while True:
        clear_screen()
        print("\nLaw Document Crawler")
        print("==================")

        if not session or not session.check_login():
            session = menu_login(debug=debug, headless=headless)
            if not session:
                input("\nPress Enter to try again...")
                continue

        clear_screen()
        print("\nLaw Document Crawler")
        print("==================")
        print("1. Process single URL")
        print("2. Batch process")
        print("3. Configure batch settings")  # New option
        print("4. Cleanup")
        print("5. Exit")

        choice = input("\nEnter your choice: ").strip()

        if choice == "1":
            menu_single_url(debug=debug, headless=headless, session=session)
        elif choice == "2":
            menu_batch_process(debug=debug, session=session)
        elif choice == "3":
            menu_batch_settings()  # New menu
        elif choice == "4":
            menu_cleanup()
        elif choice == "5":
            cleanup_and_exit()
        else:
            input("\nInvalid choice. Press Enter to continue...")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    args = parse_args()
    debug_mode = args.debug
    headless_mode = not args.no_headless
    main_menu(debug=debug_mode, headless=headless_mode)
