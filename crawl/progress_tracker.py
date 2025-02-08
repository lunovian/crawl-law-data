import os
import json
from datetime import datetime

class ProgressTracker:
    def __init__(self, file_path):
        self.file_path = file_path
        self.progress_file = f"{file_path}.progress.json"
        self.data = {
            'processed': [],  # List of processed URLs
            'failed': []     # List of failed URLs with errors
        }
        self.load_progress()

    def load_progress(self):
        """Load progress data from file"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    # Ensure backward compatibility with old format
                    if isinstance(loaded_data, dict) and 'processed' in loaded_data:
                        self.data = loaded_data
                    else:
                        self.data = {
                            'processed': [],
                            'failed': []
                        }
            except Exception as e:
                print(f"Error loading progress file: {e}")
                self.data = {
                    'processed': [],
                    'failed': []
                }

    def save_progress(self):
        """Save progress data to file"""
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving progress: {e}")

    def mark_success(self, url, status="Downloaded"):
        """Mark a URL as successfully processed"""
        if url not in self.data['processed']:
            self.data['processed'].append(url)
            # Remove from failed if present
            self.data['failed'] = [f for f in self.data['failed'] 
                                 if isinstance(f, dict) and f.get('url') != url]
            self.save_progress()

    def mark_failure(self, url, error):
        """Mark a URL as failed"""
        # Remove existing failure entry if present
        self.data['failed'] = [f for f in self.data['failed'] 
                             if isinstance(f, dict) and f.get('url') != url]
        # Add new failure entry
        self.data['failed'].append({
            'url': url,
            'error': str(error),
            'timestamp': datetime.now().isoformat()
        })
        self.save_progress()

    def is_processed(self, url):
        """Check if URL was successfully processed"""
        return url in self.data['processed']

    def get_failed_urls(self):
        """Get list of failed URLs"""
        return [f['url'] for f in self.data['failed'] if isinstance(f, dict)]

    def get_progress_summary(self):
        """Get progress summary"""
        return {
            'total_processed': len(self.data['processed']),
            'total_failed': len(self.data['failed']),
            'last_update': datetime.now().isoformat()
        }

    def clear_progress(self):
        """Clear all progress data"""
        self.data = {
            'processed': [],
            'failed': []
        }
        self.save_progress()
