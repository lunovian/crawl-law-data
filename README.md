# Law Document Crawler

A tool for automated crawling and downloading of legal documents from luatvietnam.vn

## Main Features

- Automated Google login with session management
- Single URL and batch processing support
- Interactive menu-driven interface
- Configurable batch settings
- Progress tracking with resume capability
- Automatic system resource optimization

## Menu Structure

### 1. Login Options

- Use saved credentials
- Setup/update credentials
- Automatic cookie management
- Session persistence

### 2. Process Single URL

- Direct document download
- Automatic format detection
- Progress tracking

### 3. Batch Processing

```bash
- Process all Excel files in 'batches' folder
- Select specific Excel file
- Configure batch settings
- Show download progress
- Retry failed downloads
```

### 4. Batch Configuration

```bash
- Show current settings
- Configure settings interactively
- Auto-configure based on system
- Reset to defaults
```

### 5. Cleanup Operations

```bash
- Remove duplicate PDFs
- Remove lock files
- Automatic cleanup on exit
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the crawler

```bash
python main.py [--debug] [--no-headless]
```

### 3. Setup the Google account through the menu

### 4. Place files in `batches/` folder

### 5. Begin crawling with batches

## Command Line Options

```bash
python main.py [options]

Options:
  --debug         Enable debug mode
  --no-headless   Disable headless browser mode
```

## Requirements

- Python 3.7+
- Google Chrome
- Stable internet connection
- Excel files with URLs
