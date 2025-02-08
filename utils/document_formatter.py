import os
import re
from urllib.parse import urlparse

def format_document_name(url):
    """Format a URL into a specific format."""
    try:
        # Remove the protocol part and domain
        parsed = urlparse(url)
        path = parsed.path

        # Extract base name without timestamp/random suffixes
        base = path.split('/')[-1]
        
        # Remove all extensions and fragments
        base = re.sub(r'\.(html?|aspx?|docx?|pdf)(#.*)?$', '', base)
        
        # Remove document ID suffix
        base = re.sub(r'-d\d+$', '', base)
        
        # Remove timestamp/random suffixes (common in downloaded files)
        base = re.sub(r'_\d{12,14}$', '', base)  # Remove timestamps
        base = re.sub(r'_[a-zA-Z0-9]{6,}$', '', base)  # Remove random suffixes
        
        # Replace hyphens with spaces
        base = base.replace('-', ' ')
        
        # Remove multiple spaces
        base = ' '.join(base.split())
        
        return base.strip()
        
    except Exception:
        # If any error occurs, return a cleaned version of the basename
        base = os.path.basename(url)
        return re.sub(r'\.[^.]+$', '', base)

def verify_filename_format(filename):
    """Verify if filename matches the required format"""
    formatted = format_document_name(filename)
    if formatted != filename:
        return False, f"Filename should be: {formatted}"
    return True, None

# Example usage:
if __name__ == "__main__":
    test_urls = [
        "https://luatvietnam.vn/y-te/cong-van-441-vpcp-kgvx-2020-dich-benh-viem-phoi-tai-trung-quoc-180071-d6.html#taive",
        "https://luatvietnam.vn/co-cau-to-chuc/quyet-dinh-33-qd-ubdt-uy-ban-dan-toc-180054-d1.html#taive",
    ]
    
    for name in test_urls:
        formatted = format_document_name(name)
        print(f"Original: {name}")
        print(f"Formatted: {formatted}\n")
    # Output: "cong van 441 vpcp kgvx 2020 dich benh viem phoi tai trung quoc 180071", "quyet dinh 33 qd ubdt uy ban dan toc 180054"
