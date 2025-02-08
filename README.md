# Law Document Crawler

Tool for downloading law documents from luatvietnam.vn

## Setup

1. Create and activate virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

2. Install package:

```bash
pip install -e .
```

3. First-time login:

```bash
python login.py
```

4. Run crawler:

```bash
python -m crawl.crawler [options]
```

## Usage

Place Excel files containing URLs in the `batches` folder. Each file should have:

- `Url` column: Document URLs
- `Lĩnh vực` column: Document categories
- `Ban hành` column: Issue date (dd/mm/yyyy)

## Options

- `--debug`: Enable debug mode
- `--url URL`: Process single URL
- `--workers N`: Number of download workers
- `--batch-size N`: Files per batch
- `--retry`: Retry failed downloads
- `--no-resume`: Start fresh download

## Features

- Parallel processing of URLs and files
- Robust error handling and retry mechanisms
- Session management with cookies
- Progress tracking and logging

## Requirements

You can install the required packages using the following command:

```bash
pip install -r requirements.txt
```

## Workflow

1. **Login Setup**: Run `login.py` to log in and save cookies.
2. **Prepare Excel Files**: Place your Excel files in the `batches` folder.
3. **Run the Crawler**: Run `crawl.py` with the desired arguments.

### File Structure

- `login.py`: Handles the login process and saves cookies.
- `crawl.py`: Main script to process the Excel files and download documents.
- `utils.py`: Contains utility functions and classes for downloading files, managing sessions, and logging.

### Logging

Logs are saved to `crawler.log` and include detailed information about the crawling process, including any errors encountered.

### Progress Tracking

Progress is tracked and displayed using a progress bar. The progress is also saved to a `.progress` file for each batch file, allowing the process to resume from where it left off in case of interruptions.

### Error Handling

The crawler includes robust error handling and retry mechanisms to ensure that downloads are completed successfully. If a download fails, it will be retried up to three times with increasing delays between attempts.

## License

This project is licensed under the MIT License.
