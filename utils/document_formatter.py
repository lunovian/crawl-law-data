"""
Document name formatting utilities.
Handles:
- Converting URLs to standardized filenames
- Cleaning and formatting document titles
- Verifying filename formats
- Removing invalid characters
"""

from urllib.parse import urlparse
import re


def format_document_name(url):
    """Format a URL into a standardized filename"""
    try:
        # Remove the protocol part and domain
        parsed = urlparse(url)
        path = parsed.path

        # Remove file extension and special characters
        name = path.split("/")[-1].split(".")[0]
        name = re.sub(r"[-_]+", " ", name)

        # Remove ID patterns and clean up
        name = re.sub(r"\d{6}-d\d+$", "", name)
        name = re.sub(r"[^\w\s-]", "", name)

        # Normalize whitespace
        name = " ".join(name.split())

        return name.lower()
    except Exception:
        return None


def verify_filename_format(filename):
    """Verify if filename matches the required format"""
    if not filename:
        return False

    # Check length
    if len(filename) > 255:
        return False

    # Check for invalid characters
    if re.search(r'[<>:"/\\|?*]', filename):
        return False

    return True
