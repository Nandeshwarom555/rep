import os
import logging
import requests
import time
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def upload_to_gofile(file_path, progress_callback=None):
    """
    Upload a file to Gofile.io
    
    Args:
        file_path (str): Path to the file to upload
        progress_callback (function): Callback function for progress updates
    
    Returns:
        str: URL of the uploaded file
    """
    try:
        logger.info(f"Uploading file to Gofile: {file_path}")
        
        # Get the server to upload to
        server_response = requests.get("https://api.gofile.io/getServer")
        if not server_response.ok:
            logger.error(f"Failed to get Gofile server: {server_response.text}")
            return None
        
        server_data = server_response.json()
        if server_data.get("status") != "ok":
            logger.error(f"Gofile server error: {server_data}")
            return None
        
        server = server_data.get("data", {}).get("server")
        if not server:
            logger.error("No Gofile server returned")
            return None
        
        # Upload the file
        file_size = os.path.getsize(file_path)
        
        # Custom implementation of progress tracking
        class ProgressTracker:
            def __init__(self, total_size, callback):
                self.total_size = total_size
                self.uploaded = 0
                self.callback = callback
                self.last_update = 0
            
            def update(self, chunk_size):
                self.uploaded += chunk_size
                current_time = time.time()
                # Only update progress every 0.5 seconds to avoid too many updates
                if current_time - self.last_update > 0.5:
                    progress = (self.uploaded / self.total_size) * 100
                    self.callback(progress)
                    self.last_update = current_time
        
        progress_tracker = ProgressTracker(file_size, progress_callback) if progress_callback else None
        
        with open(file_path, 'rb') as f:
            # Use a custom read function to track upload progress
            if progress_tracker:
                def read_callback(chunk):
                    progress_tracker.update(len(chunk))
                    return chunk
                
                # Create a generator that reads chunks and tracks progress
                def file_chunks():
                    chunk = f.read(8192)
                    while chunk:
                        progress_tracker.update(len(chunk))
                        yield chunk
                        chunk = f.read(8192)
                
                # Create a streaming upload for the file
                upload_response = requests.post(
                    f"https://{server}.gofile.io/uploadFile",
                    files={"file": (Path(file_path).name, file_chunks())}
                )
            else:
                # Simple upload without progress tracking
                upload_response = requests.post(
                    f"https://{server}.gofile.io/uploadFile",
                    files={"file": (Path(file_path).name, f)}
                )
        
        if not upload_response.ok:
            logger.error(f"Failed to upload file: {upload_response.text}")
            return None
        
        upload_data = upload_response.json()
        if upload_data.get("status") != "ok":
            logger.error(f"Gofile upload error: {upload_data}")
            return None
        
        # Get the download link
        download_page = upload_data.get("data", {}).get("downloadPage")
        if not download_page:
            logger.error("No download page returned from Gofile")
            return None
        
        logger.info(f"File uploaded successfully: {download_page}")
        
        # Update progress to 100% when complete
        if progress_callback:
            progress_callback(100)
        
        return download_page
    
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return None

def upload_to_catbox(file_path, progress_callback=None):
    """
    Upload a file to catbox.moe as a fallback option
    
    Args:
        file_path (str): Path to the file to upload
        progress_callback (function): Callback function for progress updates
    
    Returns:
        str: URL of the uploaded file
    """
    try:
        logger.info(f"Uploading file to Catbox: {file_path}")
        
        file_size = os.path.getsize(file_path)
        progress_tracker = None
        
        if progress_callback:
            # Custom implementation of progress tracking
            class ProgressTracker:
                def __init__(self, total_size, callback):
                    self.total_size = total_size
                    self.uploaded = 0
                    self.callback = callback
                    self.last_update = 0
                
                def update(self, chunk_size):
                    self.uploaded += chunk_size
                    current_time = time.time()
                    # Only update progress every 0.5 seconds to avoid too many updates
                    if current_time - self.last_update > 0.5:
                        progress = (self.uploaded / self.total_size) * 100
                        self.callback(progress)
                        self.last_update = current_time
            
            progress_tracker = ProgressTracker(file_size, progress_callback)
        
        with open(file_path, 'rb') as f:
            files = {'fileToUpload': (Path(file_path).name, f)}
            
            # Upload file
            response = requests.post(
                'https://catbox.moe/user/api.php',
                data={'reqtype': 'fileupload'},
                files=files
            )
        
        if not response.ok:
            logger.error(f"Failed to upload file to Catbox: {response.text}")
            return None
        
        # Catbox returns just the URL as plain text
        download_url = response.text.strip()
        
        if not download_url.startswith('https://'):
            logger.error(f"Invalid response from Catbox: {download_url}")
            return None
        
        logger.info(f"File uploaded successfully to Catbox: {download_url}")
        
        # Update progress to 100% when complete
        if progress_callback:
            progress_callback(100)
        
        return download_url
    
    except Exception as e:
        logger.error(f"Error uploading file to Catbox: {e}")
        return None
