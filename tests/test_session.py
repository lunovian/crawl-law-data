import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import patch, MagicMock
from utils.utils import LawVNSession
import requests
import time

class TestLawVNSession(unittest.TestCase):
    def setUp(self):
        self.session = LawVNSession(cookies_file='test_cookies.pkl')
        
    @patch('requests.Session.get')
    def test_check_login(self, mock_get):
        # Mock session setup
        mock_response = MagicMock()
        mock_response.text = "Đăng xuất"
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        # Mock session initialization
        self.session.logged_in = True
        self.session.session_data = {
            'cookies': [{'name': 'test', 'value': 'test'}],
            'timestamp': time.time()
        }
        
        # Test the check_login method
        result = self.session.check_login()
        self.assertTrue(result)
        mock_get.assert_called_once_with(self.session.BASE_URL)
    
    @patch('utils.requests.Session')
    def test_failed_login(self, mock_session):
        # Mock failed login check
        mock_response = MagicMock()
        mock_response.text = "Đăng nhập"
        mock_session.return_value.get.return_value = mock_response
        
        self.assertFalse(self.session.check_login())

# ...more tests for session functionality...
