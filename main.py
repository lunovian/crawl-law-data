import os
import sys
import signal
import argparse
from utils.common import setup_logger, check_setup_and_confirm
from utils.session import LawVNSession
from crawl.processor import process_document, process_batch_file, BatchSettings
from crawl.downloader import remove_duplicate_documents
import json
from crawl.progress_tracker import ProgressTracker

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Law Document Crawler')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--no-headless', action='store_true', help='Disable headless mode (show browser)')
    return parser.parse_args()

def check_login():
    """Check if login is valid"""
    try:
        if not os.path.exists('lawvn_cookies.pkl'):
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
    config_file = 'config.json'
    config = {}
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
        except:
            pass
    
    print("\nGoogle Account Setup")
    print("-------------------")
    print("Enter your Google account credentials:")
    email = input("Email: ").strip()
    password = input("Password: ").strip()
    
    config['google_credentials'] = {
        'email': email,
        'password': password
    }
    
    try:
        with open(config_file, 'w') as f:
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
    
    if choice == '1':
        if os.path.exists('config.json'):
            print("\nAttempting login...")
            
            # First try with saved cookies in headless mode
            if os.path.exists('lawvn_cookies.pkl'):
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
                if input("Would you like to update credentials? (y/n): ").lower() == 'y':
                    setup_config()
    
    elif choice == '2':
        setup_config()
        if input("\nWould you like to try logging in now? (y/n): ").lower() == 'y':
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

def menu_batch_process(debug=False, session=None):
    """Start batch processing"""
    if not session or not session.check_login():
        print("Please login first!")
        return

    print("\nBatch Processing Options:")
    print("1. Process all Excel files in 'batches' folder")
    print("2. Select specific Excel file")
    print("3. Configure batch settings")
    print("4. Show download progress")
    print("5. Retry failed downloads")
    print("6. Back")
    
    choice = input("\nEnter choice (1-6): ").strip()
    
    if choice == '1':
        if not os.path.exists('batches'):
            print("\nNo 'batches' folder found. Creating one...")
            os.makedirs('batches')
            print("\nPlease add Excel files to the 'batches' folder and try again.")
            return
            
        excel_files = [f for f in os.listdir('batches') if f.endswith(('.xlsx', '.xls'))]
        if not excel_files:
            print("\nNo Excel files found in 'batches' folder.")
            return
            
        print(f"\nFound {len(excel_files)} Excel files.")
        for excel_file in excel_files:
            file_path = os.path.join('batches', excel_file)
            print(f"\nProcessing: {excel_file}")
            process_batch_file(file_path, session=session, debug=debug, resume=True)
            
    elif choice == '2':
        if not os.path.exists('batches'):
            print("\nNo 'batches' folder found. Creating one...")
            os.makedirs('batches')
            print("\nPlease add Excel files to the 'batches' folder and try again.")
            return
            
        excel_files = [f for f in os.listdir('batches') if f.endswith(('.xlsx', '.xls'))]
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
                    file_path = os.path.join('batches', excel_files[file_num - 1])
                    print(f"\nProcessing: {excel_files[file_num - 1]}")
                    process_batch_file(file_path, session=session, debug=debug, resume=True)
                    break
            except ValueError:
                print("Please enter a valid number")
                
    elif choice == '4':
        show_download_progress()
        
    elif choice == '5':
        retry_failed_downloads(session, debug)

def show_download_progress():
    """Show progress for all batch files"""
    if not os.path.exists('batches'):
        print("\nNo batches folder found.")
        return
        
    excel_files = [f for f in os.listdir('batches') if f.endswith(('.xlsx', '.xls'))]
    if not excel_files:
        print("\nNo Excel files found.")
        return
        
    print("\nDownload Progress:")
    for file in excel_files:
        file_path = os.path.join('batches', file)
        tracker = ProgressTracker(file_path)
        progress = tracker.get_progress_summary()
        
        print(f"\n{file}:")
        print(f"- Processed: {progress['total_processed']}")
        print(f"- Failed: {progress['total_failed']}")
        if progress['last_update']:
            print(f"- Last update: {progress['last_update']}")

def retry_failed_downloads(session, debug=False):
    """Retry failed downloads from all batch files"""
    if not os.path.exists('batches'):
        print("\nNo batches folder found.")
        return
        
    excel_files = [f for f in os.listdir('batches') if f.endswith(('.xlsx', '.xls'))]
    if not excel_files:
        print("\nNo Excel files found.")
        return
        
    total_retried = 0
    for file in excel_files:
        file_path = os.path.join('batches', file)
        tracker = ProgressTracker(file_path)
        failed_urls = tracker.get_failed_urls()
        
        if failed_urls:
            print(f"\nRetrying {len(failed_urls)} failed downloads from {file}")
            for url in failed_urls:
                if process_document(url, session=session, debug=debug):
                    tracker.mark_success(url, "Retried")
                    total_retried += 1
                    
    print(f"\nRetried {total_retried} failed downloads.")

def menu_cleanup():
    """Run cleanup operations"""
    print("\nCleanup Options:")
    print("1. Remove duplicate PDFs")
    print("2. Remove lock files")
    print("3. Back")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '1':
        print("\nChecking for duplicate PDFs...")
        duplicates, space_saved = remove_duplicate_documents()
        if duplicates > 0:
            mb_saved = space_saved / (1024 * 1024)
            print(f"\nRemoved {duplicates} duplicate files")
            print(f"Saved {mb_saved:.2f} MB of space")
        else:
            print("\nNo duplicates found")
            
    elif choice == '2':
        count = 0
        for root, _, files in os.walk("downloads"):
            for file in files:
                if file.endswith('.lock'):
                    try:
                        os.unlink(os.path.join(root, file))
                        count += 1
                    except:
                        pass
        print(f"\nRemoved {count} lock files")

def cleanup_and_exit(monitor_process=None):  # We can simplify this function
    """Clean shutdown of all processes"""
    print("\nShutting down gracefully...")
    
    # Clean any lock files
    for root, _, files in os.walk("downloads"):
        for f in files:
            if f.endswith('.lock'):
                try:
                    os.unlink(os.path.join(root, f))
                except:
                    pass
    
    os._exit(0)

def signal_handler(signum, frame):
    """Handle interruption signals"""
    cleanup_and_exit()

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
        print("3. Cleanup")
        print("4. Exit")
        
        choice = input("\nEnter your choice: ").strip()
        
        if choice == '1':
            menu_single_url(debug=debug, headless=headless, session=session)
        elif choice == '2':
            menu_batch_process(debug=debug, session=session)
        elif choice == '3':
            menu_cleanup()
        elif choice == '4':  # Changed from 5 to 4
            cleanup_and_exit()
        else:
            input("\nInvalid choice. Press Enter to continue...")

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    args = parse_args()
    debug_mode = args.debug
    headless_mode = not args.no_headless
    main_menu(debug=debug_mode, headless=headless_mode)