import os
import csv
from datetime import datetime


class ProgressTracker:
    def __init__(self, source_file):
        self.source_file = source_file
        self.progress_file = self._get_progress_file()
        self.processed_urls = set()
        self.failed_urls = {}
        self.data = {"processed": set(), "failed": []}
        self.load_progress()

    def _get_progress_file(self):
        """Get progress file path based on source file"""
        base_name = os.path.splitext(self.source_file)[0]
        return f"{base_name}_progress.csv"

    def load_progress(self):
        """Load progress from CSV file"""
        if not os.path.exists(self.progress_file):
            return

        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row["url"]
                    status = row["status"]
                    if status == "success":
                        self.data["processed"].add(url)
                        self.processed_urls.add(url)
                    elif status == "failed":
                        self.data["failed"].append(
                            {
                                "url": url,
                                "error": row.get("error", ""),
                                "timestamp": row.get("timestamp", ""),
                            }
                        )
                        self.failed_urls[url] = row.get("error", "")
        except Exception as e:
            print(f"Error loading progress: {e}")

    def save_progress(self):
        """Save progress to CSV file"""
        try:
            with open(self.progress_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["url", "status", "error", "timestamp"]
                )
                writer.writeheader()

                # Write successful URLs
                for url in self.data["processed"]:
                    writer.writerow(
                        {
                            "url": url,
                            "status": "success",
                            "error": "",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                # Write failed URLs
                for failed in self.data["failed"]:
                    writer.writerow(
                        {
                            "url": failed["url"],
                            "status": "failed",
                            "error": failed["error"],
                            "timestamp": failed["timestamp"],
                        }
                    )
        except Exception as e:
            print(f"Error saving progress: {e}")

    def mark_success(self, url, note=""):
        """Mark URL as successfully processed"""
        self.data["processed"].add(url)
        self.processed_urls.add(url)
        self.save_progress()

    def mark_failure(self, url, error=""):
        """Mark URL as failed"""
        self.data["failed"].append(
            {"url": url, "error": str(error), "timestamp": datetime.now().isoformat()}
        )
        self.failed_urls[url] = error
        self.save_progress()

    def is_processed(self, url):
        """Check if URL has been processed"""
        return url in self.data["processed"]

    def get_processed_urls(self):
        """Get list of processed URLs"""
        return list(self.data["processed"])

    def get_failed_urls(self):
        """Get list of failed URLs"""
        return [item["url"] for item in self.data["failed"]]

    def get_progress_summary(self):
        """Get progress summary"""
        return {
            "total_processed": len(self.data["processed"]),
            "total_failed": len(self.data["failed"]),
            "last_update": datetime.now().isoformat(),
        }

    def clear_progress(self):
        """Clear all progress data"""
        self.data = {"processed": set(), "failed": []}
        self.save_progress()

    def get_pending_urls(self):
        """Get list of URLs that still need processing"""
        return [url for url in self.failed_urls]
