import unittest
import pandas as pd
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from crawl.crawler import safe_split_fields, process_url_chunk, DownloadStats

class TestCrawler(unittest.TestCase):
    def test_safe_split_fields(self):
        test_cases = [
            ("field1;field2", ["field1", "field2"]),  # Normal case
            ("", [""]),                               # Empty string
            (None, ["unknown"]),                      # None value
            (pd.NA, ["unknown"]),                     # pandas NA
            ("field1;;field2", ["field1", "field2"]),  # Multiple delimiters
            ("  field1  ;  field2  ", ["field1", "field2"]),  # Extra spaces
            (";", [""]),                              # Just delimiter
            ("  ;  ", [""])                           # Spaces and delimiter
        ]
        
        for input_value, expected in test_cases:
            with self.subTest(msg=f"Input: {input_value}"):
                result = safe_split_fields(input_value)
                self.assertEqual(result, expected)
    
    def test_download_stats(self):
        stats = DownloadStats()
        stats.add_success('.pdf')
        stats.add_success('.doc')
        stats.add_success('.pdf')
        
        summary = stats.get_summary()
        self.assertEqual(summary['pdf'], 2)
        self.assertEqual(summary['doc'], 1)
        self.assertEqual(summary['total'], 3)
