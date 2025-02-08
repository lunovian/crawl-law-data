import pytest
import os
import tempfile

@pytest.fixture
def temp_folder():
    """Provide a temporary folder for test files"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    import shutil
    shutil.rmtree(temp_dir)

@pytest.fixture
def sample_excel():
    """Create a sample Excel file for testing"""
    import pandas as pd
    
    df = pd.DataFrame({
        'Url': ['http://example.com/1', 'http://example.com/2'],
        'Lĩnh vực': ['field1;field2', 'field3'],
        'Ban hành': ['01/01/2023', '02/02/2023']
    })
    
    temp_file = os.path.join(tempfile.mkdtemp(), 'test.xlsx')
    df.to_excel(temp_file, index=False)
    
    yield temp_file
    
    os.unlink(temp_file)
