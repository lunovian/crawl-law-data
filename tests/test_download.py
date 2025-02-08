import unittest
import os
import tempfile
from unittest.mock import patch, MagicMock
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.utils import download_file, _do_download, DownloadStatus

class TestDownload(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_url = "https://example.com/test.pdf"
        self.test_file = "test.pdf"
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('utils.requests.get')
    def test_successful_download(self, mock_get):
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content.return_value = [b"test content"]
        mock_get.return_value = mock_response
        
        success, error = download_file(self.test_url, self.test_file, self.temp_dir)
        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, self.test_file)))
    
    def test_download_status(self):
        status = DownloadStatus()
        status.add_success("url1", "file1.pdf")
        status.add_failure("url2", "404 error")
        
        summary = status.get_summary()
        self.assertEqual(len(summary['successful']), 1)
        self.assertEqual(len(summary['failed']), 1)

# ...more tests for download functionality...
