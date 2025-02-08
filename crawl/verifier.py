import os
import json
import pandas as pd
import subprocess
from tqdm import tqdm

def load_progress(progress_file):
    """Load progress from JSON file"""
    if os.path.exists(progress_file):
        with open(progress_file, 'r') as f:
            return json.load(f)
    return {}

def safe_split_fields(value):
    """Safely handle field splitting with error checking"""
    if pd.isna(value):  # Handle NaN/None values
        return ['unknown']
    try:
        return [field.strip() for field in str(value).split(';') if field.strip()]
    except:
        return ['unknown']

def check_file_setup():
    """Check if all required files and folders are present"""
    required_setup = {
        'cookies': os.path.exists('lawvn_cookies.pkl'),
        'batches_folder': os.path.exists('batches'),
        'has_excel': False,
        'downloads_folder': os.path.exists('downloads')
    }
    
    if required_setup['batches_folder']:
        excel_files = [f for f in os.listdir('batches') if f.endswith(('.xlsx', '.xls'))]
        required_setup['has_excel'] = bool(excel_files)
    
    return required_setup

def check_missing_downloads(batches_folder="batches", downloads_folder="downloads"):
    """Check for missing downloads in each URL"""
    excel_files = [f for f in os.listdir(batches_folder) if f.endswith(('.xlsx', '.xls'))]
    missing_downloads = []
    total_checked = 0
    total_files = 0

    # First count total files to check
    for excel_file in excel_files:
        file_path = os.path.join(batches_folder, excel_file)
        df = pd.read_excel(file_path)
        total_files += len(df)

    # Create progress bar
    with tqdm(total=total_files, desc="Checking files") as pbar:
        for excel_file in excel_files:
            file_path = os.path.join(batches_folder, excel_file)
            progress_file = f"{file_path}.progress"
            progress_data = load_progress(progress_file)

            df = pd.read_excel(file_path)
            if 'Url' not in df.columns:
                print(f"Excel file {file_path} must contain a 'Url' column")
                continue

            # Fill NaN values with default
            df['Lĩnh vực'] = df['Lĩnh vực'].fillna('unknown')
            df['Ban hành'] = pd.to_datetime(df['Ban hành'], format='%d/%m/%Y', dayfirst=True, errors='coerce')
            df['Ban hành'] = df['Ban hành'].fillna(pd.Timestamp.now())

            for index, row in df.iterrows():
                url = row['Url']
                fields = safe_split_fields(row['Lĩnh vực'])
                year = str(row['Ban hành'].year)

                if str(index) in progress_data and progress_data[str(index)]['success']:
                    expected_files = progress_data[str(index)]['files']
                    for field in fields:
                        for expected_file in expected_files:
                            expected_path = os.path.join(downloads_folder, str(field), year, os.path.basename(expected_file))
                            if not os.path.exists(expected_path):
                                missing_downloads.append((url, expected_path))
                
                total_checked += 1
                pbar.update(1)
                pbar.set_postfix({'Missing': len(missing_downloads)})

    return missing_downloads

def handle_user_choice(missing_downloads=None):
    """Handle user choices based on system state"""
    setup = check_file_setup()
    
    if not all([setup['cookies'], setup['batches_folder'], setup['has_excel']]):
        print("\nMissing required setup:")
        if not setup['cookies']:
            print("- No cookies file found. Run 'python login.py' first")
        if not setup['batches_folder']:
            print("- No 'batches' folder found")
        elif not setup['has_excel']:
            print("- No Excel files found in 'batches' folder")
            
        choice = input("\nDo you want to set up the missing components first? (yes/no): ")
        if choice.lower() == 'yes':
            if not setup['cookies']:
                subprocess.run(["python", "login.py"])
            if not setup['batches_folder']:
                os.makedirs('batches')
                print("\nCreated 'batches' folder. Please add your Excel files and run again.")
            return False
        return False
    
    if missing_downloads:
        print(f"\nFound {len(missing_downloads)} missing files.")
        print("\nOptions:")
        print("1. Download only missing files")
        print("2. Retry all downloads")
        print("3. Exit")
        
        while True:
            choice = input("\nEnter your choice (1-3): ").strip()
            if choice == '1':
                subprocess.run(["python", "crawl.py", "--retry"])
                break
            elif choice == '2':
                subprocess.run(["python", "crawl.py", "--no-resume"])
                break
            elif choice == '3':
                print("\nExiting...")
                break
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")
    else:
        print("\nAll files are present and complete!")
        print("\nOptions:")
        print("1. Re-download all files")
        print("2. Exit")
        
        while True:
            choice = input("\nEnter your choice (1-2): ").strip()
            if choice == '1':
                confirm = input("This will re-download all files. Are you sure? (yes/no): ")
                if confirm.lower() == 'yes':
                    subprocess.run(["python", "crawl.py", "--no-resume"])
                break
            elif choice == '2':
                print("\nExiting...")
                break
            else:
                print("Invalid choice. Please enter 1 or 2.")

def main():
    if not check_file_setup()['cookies']:
        print("\nNo cookies file found. Please run 'python login.py' first.")
        return
        
    print("\nChecking system setup and missing downloads...")
    missing_downloads = check_missing_downloads()
    handle_user_choice(missing_downloads)

if __name__ == "__main__":
    main()
