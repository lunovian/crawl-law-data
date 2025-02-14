# Law Document Crawler

A tool for automated crawling and downloading of legal documents from luatvietnam.vn

## 🛠️ Main Features

- ✅ Automated Google login with session management
- 🌐 Single URL and batch processing support
- 🖥️ Interactive menu-driven interface
- ⚙️ Configurable batch settings
- 🔄 Progress tracking with resume capability
- 🚀 Automatic system resource optimization
- 🗑️ Duplicate file detection and removal
- 📂 Dynamic filename generation with collision avoidance

---

## 📋 Menu Structure

### 1️⃣ Login Options

- 🔐 Use saved credentials
- 🛠️ Setup/update credentials
- 🍪 Automatic cookie management
- 🔄 Session persistence

### 2️⃣ Process Single URL

- 🔍 Direct document download
- 🧠 Automatic format detection
- 📝 Progress tracking
- 🔄 Filename sanitization to avoid invalid characters

### 3️⃣ Batch Processing

```bash
- 📑 Process all Excel files in 'batches' folder
- 📂 Select specific Excel file
- ⚙️ Configure batch settings
- 📊 Show download progress
- 🔁 Retry failed downloads with retry_mode
```

### 4️⃣ Batch Configuration

```bash
- 🔎 Show current settings
- ⚙️ Configure settings interactively
- 🤖 Auto-configure based on system
- 🔄 Reset to defaults
```

### 5️⃣ Cleanup Operations

```bash
- 🗑️ Remove duplicate PDFs
- 🔐 Remove lock files
- 🔄 Automatic cleanup on exit
```

---

## ⚙️ **Technical Details**

### 📂 Folder Structure

- **`crawl/`**: Main crawling logic, including file downloads and batch processing.
- **`downloads/`**: Contains all downloaded documents.
- **`logs/`**: Logs application events and errors.
- **`utils/`**: Utility functions for logging, file formatting, and session management.
- **`main.py`**: Entry point for application execution.
- **`config.json`**: Stores configurations like credentials, batch settings, and download preferences.

### 🔑 File Naming Mechanism

- File names are formatted by removing invalid characters and limiting the length to 255 characters.
- Each URL is assigned a **hash (URL hash)** to ensure uniqueness.
- Filename structure: `prefix_timestamp_urlhash.extension`

**Example:** `quyet dinh 1756 qd bgtvt bo giao thong van tai 53709 d1.doc`

### 🛑 Duplicate Detection

- Duplicate file removal occurs after all files have been downloaded.
- The `remove_duplicate_documents()` function scans for duplicate PDFs when DOC or DOCX versions exist.
- The detection is based on file content, not just the filename.

### ⚙️ Batch Configuration Settings

Configurable parameters:
- **`chunk_size`**: The size of each data chunk.
- **`max_workers`**: The number of concurrent threads.
- **`batch_size`**: The number of URLs processed simultaneously.
- **`max_tabs`**: The maximum number of browser tabs.
- **`retry_mode`**: Enable or disable retry for failed downloads.

### 🧠 Retry Mode (`retry_mode`)

- **Purpose:** Retry downloads when encountering errors (e.g., network issues, server failures).
- **Values:**
  - `True`: Retry downloads up to the configured limit.
  - `False`: Skip failed files.

### 🖼️ File Naming and Deduplication

- File names are generated based on the URL's hash.
- Duplicate files are removed post-download using `remove_duplicate_documents()`.

---

## ⚙️ **Setup Guide**

### 1️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 2️⃣ Run the crawler

```bash
python main.py [--debug] [--no-headless]
```

### 3️⃣ Configure Google account through the interactive menu

### 4️⃣ Place files in `batches/` folder

### 5️⃣ Start crawling with batch processing

---

## 🖥️ **Command Line Options**

```bash
python main.py [options]

Options:
  --debug         Enable debug mode
  --no-headless   Disable headless browser mode
```

---

## 🛠️ **System Requirements**

- 🐍 Python 3.7+
- 🌐 Google Chrome
- 📡 Stable internet connection
- 📑 Excel files with URLs


