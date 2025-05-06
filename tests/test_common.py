import unittest
import os
import sys
import json
from unittest.mock import patch, MagicMock

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestCommonDB(unittest.TestCase):
    """Test cases for the common.db module"""
    
    @patch('common.db.psycopg2.pool')
    def test_connection_pool(self, mock_pool):
        """Test that the connection pool is created and used correctly"""
        # Setup mock
        mock_conn = MagicMock()
        mock_pool.SimpleConnectionPool.return_value = MagicMock()
        mock_pool.SimpleConnectionPool.return_value.getconn.return_value = mock_conn
        
        # Import after mocking
        from common.db import get_postgres_connection
        
        # Test connection acquisition
        with get_postgres_connection() as conn:
            self.assertEqual(conn, mock_conn)
            
        # Verify pool creation and connection release
        mock_pool.SimpleConnectionPool.assert_called_once()
        mock_pool.SimpleConnectionPool.return_value.putconn.assert_called_once_with(mock_conn)
        
    @patch('common.db.get_postgres_connection')
    def test_execute_query(self, mock_get_conn):
        """Test that execute_query properly executes SQL and returns results"""
        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn
        
        # Mock fetchall results
        expected_results = [{"id": 1, "name": "test"}]
        mock_cursor.fetchall.return_value = expected_results
        mock_cursor.description = True  # Indicate there are results
        
        # Import after mocking
        from common.db import execute_query
        
        # Test query execution
        test_query = "SELECT * FROM test_table"
        test_params = {"param1": "value1"}
        
        results = execute_query(test_query, test_params)
        
        # Verify function behavior
        mock_cursor.execute.assert_called_once_with(test_query, test_params)
        mock_cursor.fetchall.assert_called_once()
        self.assertEqual(results, expected_results)
        
    @patch('common.db.execute_query')
    def test_get_active_model_info(self, mock_execute):
        """Test that get_active_model_info returns the correct model info"""
        # Setup mock results
        expected_model = {
            "model_id": "test-model-id",
            "version_tag": "v0.75-2023-12-31",
            "artifact_url": "/models/test-model",
            "train_auc": 0.75,
            "train_date": "2023-12-31"
        }
        mock_execute.return_value = [expected_model]
        
        # Import after mocking
        from common.db import get_active_model_info
        
        # Test function
        model_info = get_active_model_info()
        
        # Verify function behavior
        self.assertEqual(model_info, expected_model)
        
        # Test default response when no model found
        mock_execute.return_value = []
        model_info = get_active_model_info()
        
        # Should return default model info
        self.assertEqual(model_info["version_tag"], "v0.1.0-default")
        self.assertEqual(model_info["model_id"], "default")
        
if __name__ == '__main__':
    unittest.main() 