"""
Error logging and debug information management.
Provides:
- HTML content logging
- Screenshot capture
- Error tracking with timestamps
- Daily log organization
- JSON-based error recording
"""

import os
import logging
import json
from datetime import datetime

class ErrorLogger:
    def __init__(self, base_dir="logs"):
        self.base_dir = base_dir
        self.setup_directories()
        
    def setup_directories(self):
        """Create required logging directories"""
        today = datetime.now().strftime("%Y-%m-%d")
        dirs = [
            os.path.join(self.base_dir, "html"),
            os.path.join(self.base_dir, "screenshots"),
            os.path.join(self.base_dir, "errors")
        ]
        for dir_path in dirs:
            daily_dir = os.path.join(dir_path, today)
            if not os.path.exists(daily_dir):
                os.makedirs(daily_dir)

    def get_log_path(self, category, filename):
        """Get path for log file with date-based organization"""
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.base_dir, category, today, filename)

    def save_html(self, html_content, prefix="error", url=None):
        """Save HTML content with timestamp"""
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{prefix}_{timestamp}.html"
        if url:
            # Add URL hash to filename to avoid collisions
            url_hash = abs(hash(url)) % 10000
            filename = f"{prefix}_{timestamp}_{url_hash}.html"
            
        filepath = self.get_log_path("html", filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return filepath
        except Exception as e:
            logging.error(f"Failed to save HTML: {str(e)}")
            return None

    def save_screenshot(self, screenshot, prefix="error", url=None):
        """Save screenshot with timestamp"""
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        if url:
            url_hash = abs(hash(url)) % 10000
            filename = f"{prefix}_{timestamp}_{url_hash}.png"
            
        filepath = self.get_log_path("screenshots", filename)
        try:
            screenshot.save(filepath)
            return filepath
        except Exception as e:
            logging.error(f"Failed to save screenshot: {str(e)}")
            return None

    def log_error(self, error_info, html=None, screenshot=None, url=None):
        """Log error with associated HTML and screenshots"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        error_entry = {
            "timestamp": timestamp,
            "error": str(error_info),
            "url": url,
            "html_file": None,
            "screenshot_file": None
        }

        if html:
            html_path = self.save_html(html, "error", url)
            error_entry["html_file"] = html_path

        if screenshot:
            screenshot_path = self.save_screenshot(screenshot, "error", url)
            error_entry["screenshot_file"] = screenshot_path

        # Save error details to JSON
        self._save_error_log(error_entry)
        return error_entry

    def _save_error_log(self, error_entry):
        """Save error details to JSON log file"""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(self.base_dir, "errors", today, "error_log.json")
        
        try:
            existing_logs = []
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    existing_logs = json.load(f)
            
            existing_logs.append(error_entry)
            
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(existing_logs, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logging.error(f"Failed to save error log: {str(e)}")
