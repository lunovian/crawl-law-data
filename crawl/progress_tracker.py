import os
import csv
from datetime import datetime
import shutil


class ProgressTracker:
    def __init__(self, file_path):
        self.file_path = file_path
        self.progress_file = f"{file_path}.progress.csv"
        self.progress = {  # Changed back to progress instead of data
            "processed": [],
            "failed": [],
        }
        self.load_progress()

    def load_progress(self):
        """Load progress from CSV with error handling"""
        if os.path.exists(self.progress_file):
            try:
                self.progress = {
                    "processed": [],
                    "failed": [],
                }  # Use progress instead of data
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["status"] == "success":
                            self.progress["processed"].append(row["url"])
                        else:
                            self.progress["failed"].append(
                                {
                                    "url": row["url"],
                                    "error": row["error"],
                                    "timestamp": row["timestamp"],
                                }
                            )
            except Exception as e:
                print(f"Error loading progress: {e}")
                # Make backup of problematic file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup = f"{self.progress_file}.{timestamp}.bak"
                try:
                    shutil.copy2(self.progress_file, backup)
                    print(f"Created backup at {backup}")
                except:
                    pass
                # Reset progress
                self.progress = {"processed": [], "failed": []}
                self.save_progress()

    def save_progress(self):
        """Save progress to CSV with atomic write"""
        temp_file = f"{self.progress_file}.tmp"
        try:
            fieldnames = ["url", "status", "error", "timestamp"]

            with open(temp_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                # Write successful URLs
                for url in self.progress["processed"]:  # Use progress instead of data
                    writer.writerow(
                        {
                            "url": url,
                            "status": "success",
                            "error": "",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                # Write failed URLs
                for fail in self.progress["failed"]:  # Use progress instead of data
                    writer.writerow(
                        {
                            "url": fail["url"],
                            "status": "failed",
                            "error": fail["error"],
                            "timestamp": fail["timestamp"],
                        }
                    )

            # Atomic replace
            if os.path.exists(self.progress_file):
                os.replace(temp_file, self.progress_file)
            else:
                os.rename(temp_file, self.progress_file)

        except Exception as e:
            print(f"Error saving progress: {e}")
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except:
                    pass

    def mark_success(self, url, status="Downloaded"):
        """Mark a URL as successfully processed"""
        if url not in self.progress["processed"]:
            self.progress["processed"].append(url)
            # Remove from failed if present
            self.progress["failed"] = [
                f
                for f in self.progress["failed"]
                if isinstance(f, dict) and f.get("url") != url
            ]
            self.save_progress()

    def mark_failure(self, url, error):
        """Mark a URL as failed"""
        # Remove existing failure entry if present
        self.progress["failed"] = [
            f
            for f in self.progress["failed"]
            if isinstance(f, dict) and f.get("url") != url
        ]
        # Add new failure entry
        self.progress["failed"].append(
            {"url": url, "error": str(error), "timestamp": datetime.now().isoformat()}
        )
        self.save_progress()

    def is_processed(self, url):
        """Check if URL was successfully processed"""
        return url in self.progress["processed"]

    def get_failed_urls(self):
        """Get list of failed URLs"""
        return [f["url"] for f in self.progress["failed"] if isinstance(f, dict)]

    def get_progress_summary(self):
        """Get progress summary"""
        return {
            "total_processed": len(self.progress["processed"]),
            "total_failed": len(self.progress["failed"]),
            "last_update": datetime.now().isoformat(),
        }

    def clear_progress(self):
        """Clear all progress data"""
        self.progress = {"processed": [], "failed": []}
        self.save_progress()

    def get_processed_urls(self):
        """Get list of successfully processed URLs"""
        return self.progress["processed"]

    def get_pending_urls(self):
        """Get list of URLs that still need processing"""
        return [url for url in self.progress["failed"]]
