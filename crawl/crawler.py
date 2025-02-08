import os
import sys
import signal
import argparse
from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
from multiprocessing import Process
from utils.common import setup_logger, check_setup_and_confirm, DownloadStats
from monitor.monitor import ProcessMonitor
from crawl.processor import process_document, process_excel_file
from utils.session import LawVNSession  # Updated import
from crawl.downloader import remove_duplicate_documents

def signal_handler(signum, frame):
    """Handle Ctrl+C by cleaning up lock files"""
    print("\nCleaning up and exiting...")
    # Remove any remaining lock files
    for root, dirs, files in os.walk("downloads"):
        for f in files:
            if f.endswith('.lock'):
                try:
                    os.unlink(os.path.join(root, f))
                except:
                    pass
    sys.exit(0)

def main():
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    parser = argparse.ArgumentParser(description='Crawl law documents')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--url', help='Debug single URL')
    parser.add_argument('--no-resume', action='store_true', help='Disable resume capability')
    parser.add_argument('--workers', type=int, help='Number of download workers (default: auto)')
    parser.add_argument('--batch-size', type=int, default=5, help='Number of files to process in each batch (default: 5)')
    parser.add_argument('--retry', action='store_true', help='Retry failed downloads without file locking')
    args = parser.parse_args()

    logger = setup_logger(args.debug)  # Make sure logger is defined early
    session = LawVNSession(debug=args.debug)

    if not os.path.exists('lawvn_cookies.pkl'):
        print("\nNo cookies file found!")
        print("Please run 'python login.py' first to create login session")
        return

    if not session.check_login():
        print("\nCookies expired or invalid!")
        print("Please run 'python login.py' to create new login session")
        return

    if args.debug:
        logger.info("Successfully loaded login session")

    if args.url:
        logger.info(f"Debugging single URL: {args.url}")
        success = process_document(args.url, session=session, debug=args.debug)
        if not success:
            logger.error("Failed to process document")
        return

    if not args.url:  # Skip for single URL debug mode
        setup_choice = check_setup_and_confirm()
        if setup_choice['action'] == 'exit':
            print("\nExiting...")
            return
        elif setup_choice['action'] == 'retry':
            args.retry = True
        args.no_resume = not setup_choice['resume']

    batches_folder = "batches"
    if not os.path.exists(batches_folder):
        print(f"Creating batches folder: {batches_folder}")
        os.makedirs(batches_folder)
        print("Please place your Excel files in the batches folder")
        return

    excel_files = [f for f in os.listdir(batches_folder) 
                  if f.endswith(('.xlsx', '.xls'))]
    
    if not excel_files:
        print("No Excel files found in batches folder")
        return

    # Start performance monitoring in a separate process
    monitor_process = Process(target=ProcessMonitor().monitor, kwargs={'duration': 3600})  # Monitor for 1 hour
    monitor_process.start()

    try:
        # Process files with process pool
        chunk_size = 50  # Larger chunks for better efficiency
        max_processes = min(os.cpu_count() - 1 or 1, 4)  # Limit max processes
        workers_per_process = 4  # Fixed worker count per process

        print(f"\nPerformance Configuration:")
        print(f"- Processes: {max_processes}")
        print(f"- Workers per process: {workers_per_process}")
        print(f"- Chunk size: {chunk_size}")
        print(f"- Total parallel tasks: {max_processes * workers_per_process}")

        total_stats = DownloadStats()
        
        # Process all Excel files in parallel
        total_stats = DownloadStats()
        file_args = [
            (
                os.path.join(batches_folder, excel_file),
                {'cookies_file': 'lawvn_cookies.pkl', 'debug': args.debug},
                {
                    'debug': args.debug,
                    'workers_per_process': workers_per_process,
                    'inner_batch_size': 5,
                    'retry_mode': args.retry,
                    'chunk_size': chunk_size,
                    'max_processes': max_processes
                }
            )
            for excel_file in excel_files
        ]

        with ProcessPoolExecutor(max_workers=len(excel_files)) as executor:
            futures = [executor.submit(process_excel_file, args) for args in file_args]
            
            total_completed = 0
            for future, excel_file in zip(concurrent.futures.as_completed(futures), excel_files):
                stats, completed = future.result()
                total_completed += completed
                
                # Update total stats
                total_stats.success_count['.doc'] += stats.success_count['.doc']
                total_stats.success_count['.pdf'] += stats.success_count['.pdf']
                total_stats.total_files += stats.total_files
                
                print(f"\nCompleted {excel_file}:")
                print(f"URLs processed: {completed}")
                print(f"Files: {stats.success_count['.doc']} DOC, {stats.success_count['.pdf']} PDF")

        # Show final summary
        print("\nFinal Download Summary:")
        print(f"Total URLs processed: {total_completed}")
        print(f"Total files downloaded: {total_stats.total_files}")
        print(f"DOC files: {total_stats.success_count['.doc']}")
        print(f"PDF files: {total_stats.success_count['.pdf']}")
        
        # Add duplicate removal
        if input("\nWould you like to remove duplicate PDF files? (y/n): ").lower() == 'y':
            duplicates, space_saved = remove_duplicate_documents()
            if duplicates > 0:
                print("\nDuplicate removal complete!")
                print(f"You can find a detailed log in crawler.log")

    finally:
        monitor_process.terminate()
        monitor_process.join()

if __name__ == "__main__":
    main()
