import os
import logging
import subprocess
import json
import tempfile
import time
import asyncio
import aiohttp
import requests
from pathlib import Path
import uuid

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def sync_download_video(url, temp_dir):
    """
    Download a video from a URL to a temporary directory (synchronous version)
    
    Args:
        url (str): The URL of the video to download
        temp_dir (Path): The temporary directory to save the video
    
    Returns:
        Path: The path to the downloaded video file
    """
    logger.info(f"Downloading video from {url}")
    
    try:
        # Create a unique filename for the downloaded video
        video_name = f"video_{uuid.uuid4().hex}"
        video_path = temp_dir / video_name
        
        # Download the video using requests
        response = requests.get(url, stream=True)
        if response.status_code != 200:
            logger.error(f"Failed to download video: HTTP {response.status_code}")
            return None
        
        # Get content type to determine file extension
        content_type = response.headers.get('Content-Type', '')
        extension = get_extension_from_content_type(content_type)
        
        # If we couldn't determine extension from content type, try to get it from URL
        if not extension:
            extension = url.split('.')[-1] if '.' in url else 'mp4'
        
        # Final video path with extension
        final_path = video_path.with_suffix(f".{extension}")
        
        # Download the content
        with open(final_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Verify if the downloaded file is a valid video
        if is_valid_video(final_path):
            logger.info(f"Video downloaded successfully to {final_path}")
            return final_path
        else:
            logger.error(f"Downloaded file is not a valid video")
            return None
    
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None

async def download_video(url, temp_dir):
    """
    Download a video from a URL to a temporary directory
    
    Args:
        url (str): The URL of the video to download
        temp_dir (Path): The temporary directory to save the video
    
    Returns:
        Path: The path to the downloaded video file
    """
    logger.info(f"Downloading video from {url}")
    
    try:
        # Create a unique filename for the downloaded video
        video_name = f"video_{uuid.uuid4().hex}"
        video_path = temp_dir / video_name
        
        # Download the video using aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to download video: HTTP {response.status}")
                    return None
                
                # Get content type to determine file extension
                content_type = response.headers.get('Content-Type', '')
                extension = get_extension_from_content_type(content_type)
                
                # If we couldn't determine extension from content type, try to get it from URL
                if not extension:
                    extension = url.split('.')[-1] if '.' in url else 'mp4'
                
                # Final video path with extension
                final_path = video_path.with_suffix(f".{extension}")
                
                # Download the content
                with open(final_path, 'wb') as f:
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                
                # Verify if the downloaded file is a valid video
                if is_valid_video(final_path):
                    logger.info(f"Video downloaded successfully to {final_path}")
                    return final_path
                else:
                    logger.error(f"Downloaded file is not a valid video")
                    return None
    
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None

def get_extension_from_content_type(content_type):
    """Get file extension from content type"""
    content_type_map = {
        'video/mp4': 'mp4',
        'video/webm': 'webm',
        'video/x-matroska': 'mkv',
        'video/quicktime': 'mov',
        'video/x-msvideo': 'avi',
        'video/x-flv': 'flv',
        'video/mpeg': 'mpeg',
        'video/3gpp': '3gp',
        'video/ogg': 'ogv',
    }
    
    return content_type_map.get(content_type.lower(), '')

def is_valid_video(file_path):
    """Check if a file is a valid video using ffprobe"""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-select_streams', 'v:0', 
            '-show_entries', 'stream=codec_type', 
            '-of', 'json', 
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"ffprobe error: {result.stderr}")
            return False
        
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        
        # Check if there's at least one video stream
        return any(stream.get('codec_type') == 'video' for stream in streams)
    
    except Exception as e:
        logger.error(f"Error verifying video: {e}")
        return False

def get_video_info(file_path):
    """Get information about a video file using ffprobe"""
    try:
        cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-select_streams', 'v:0', 
            '-show_entries', 'stream=width,height,codec_name,duration', 
            '-of', 'json', 
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"ffprobe error: {result.stderr}")
            return {}
        
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        
        if not streams:
            return {}
        
        stream = streams[0]
        
        # Get format information
        format_cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'format=format_name,duration,size', 
            '-of', 'json', 
            str(file_path)
        ]
        format_result = subprocess.run(format_cmd, capture_output=True, text=True)
        format_data = json.loads(format_result.stdout)
        format_info = format_data.get('format', {})
        
        # Create video info dictionary
        video_info = {
            'width': int(stream.get('width', 0)),
            'height': int(stream.get('height', 0)),
            'codec': stream.get('codec_name', 'unknown'),
            'format': format_info.get('format_name', 'unknown'),
            'size': int(format_info.get('size', 0)),
            'duration': float(stream.get('duration') or format_info.get('duration', 0))
        }
        
        return video_info
    
    except Exception as e:
        logger.error(f"Error getting video info: {e}")
        return {}

def merge_videos(video_paths, output_path, progress_callback=None, timeout=1800, use_reencode=False):
    """
    Merge multiple videos into one using FFmpeg
    
    Args:
        video_paths (list): List of paths to video files
        output_path (str): Path where the merged video will be saved
        progress_callback (function): Callback function for progress updates
        timeout (int): Maximum time in seconds to wait for FFmpeg to complete (default: 30 minutes)
        use_reencode (bool): Whether to re-encode videos (helps with incompatible formats)
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not video_paths:
        logger.error("No videos provided for merging")
        return False
    
    try:
        # First check if all videos have the same codec/format
        video_infos = [get_video_info(path) for path in video_paths]
        if not video_infos or any(not info for info in video_infos):
            logger.error("Failed to get info for one or more videos")
            return False
        
        # Check for format compatibility
        codecs = [info.get('codec') for info in video_infos]
        resolutions = [(info.get('width'), info.get('height')) for info in video_infos]
        
        logger.info(f"Video codecs: {codecs}")
        logger.info(f"Video resolutions: {resolutions}")
        
        # Determine if we need to force re-encoding
        force_reencode = use_reencode
        if len(set(codecs)) > 1:
            logger.warning(f"Multiple codecs detected: {set(codecs)}. Consider re-encoding.")
            force_reencode = True
        
        # Create a temporary file list for ffmpeg
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            file_list_path = f.name
            for video_path in video_paths:
                f.write(f"file '{video_path}'\n")
        
        # Calculate total duration for progress tracking
        total_duration = sum(info.get('duration', 0) for info in video_infos)
        
        # Prepare FFmpeg command
        if force_reencode:
            logger.info("Using re-encoding for better compatibility")
            # Get the most common resolution to standardize the output
            heights = [info.get('height', 0) for info in video_infos if info.get('height', 0) > 0]
            if not heights:
                target_height = 720  # Default to 720p if can't determine
            else:
                target_height = max(set(heights), key=heights.count)
            
            # Use re-encoding for better compatibility
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file if it exists
                '-f', 'concat',
                '-safe', '0',
                '-i', file_list_path,
                '-c:v', 'libx264',  # Use H.264 codec for video
                '-crf', '23',       # Constant rate factor (quality)
                '-preset', 'medium', # Encoding speed/compression ratio
                '-c:a', 'aac',      # Use AAC codec for audio
                '-b:a', '128k',     # Audio bitrate
                '-vf', f'scale=-2:{target_height}', # Scale to target height
                '-movflags', '+faststart',  # Optimize for web streaming
                output_path
            ]
        else:
            # Simple stream copy (faster, but may fail with incompatible formats)
            cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file if it exists
                '-f', 'concat',
                '-safe', '0',
                '-i', file_list_path,
                '-c', 'copy',  # Copy streams without re-encoding
                '-movflags', '+faststart',  # Optimize for web streaming
                output_path
            ]
        
        logger.debug(f"Running FFmpeg command: {' '.join(cmd)}")
        
        # Start the process with a timeout
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Variables to track process state
        start_time = time.time()
        last_progress_time = start_time
        last_progress_value = 0
        stalled_time = 0
        
        # Track progress
        if progress_callback:
            while process.poll() is None:
                # Check if we've exceeded the timeout
                current_time = time.time()
                elapsed = current_time - start_time
                if elapsed > timeout:
                    logger.error(f"FFmpeg process timed out after {timeout} seconds")
                    process.terminate()
                    return False
                
                # Read output line
                output = process.stderr.readline()
                if "time=" in output:
                    # Extract time
                    try:
                        time_str = output.split("time=")[1].split()[0]
                        if ":" in time_str:
                            time_parts = time_str.split(":")
                            if len(time_parts) == 3:
                                hours, minutes, seconds = time_parts
                                current_time_value = (float(hours) * 3600) + (float(minutes) * 60) + float(seconds)
                                progress = min(100, (current_time_value / total_duration) * 100)
                                
                                # Check if progress is stalled
                                if progress > last_progress_value:
                                    last_progress_value = progress
                                    last_progress_time = current_time
                                    stalled_time = 0
                                else:
                                    stalled_time = current_time - last_progress_time
                                
                                # If progress is stalled for too long (2 minutes), abort
                                if stalled_time > 120:
                                    logger.error(f"FFmpeg process appears to be stalled for {stalled_time:.1f} seconds")
                                    process.terminate()
                                    
                                    # If we weren't already re-encoding, try again with re-encoding
                                    if not force_reencode:
                                        logger.info("Trying again with re-encoding enabled")
                                        return merge_videos(video_paths, output_path, progress_callback, timeout, True)
                                    return False
                                
                                progress_callback(progress)
                    except Exception as e:
                        logger.error(f"Error parsing FFmpeg progress: {e}")
                
                # Check for signs of incompatibility in output
                if "invalid dropping" in output:
                    stalled_warnings_count = getattr(process, 'stalled_warnings_count', 0) + 1
                    setattr(process, 'stalled_warnings_count', stalled_warnings_count)
                    
                    # If we see too many stalled warnings, abort and try re-encoding
                    if stalled_warnings_count > 100 and not force_reencode:
                        logger.warning("Too many 'invalid dropping' warnings, likely incompatible formats")
                        process.terminate()
                        logger.info("Trying again with re-encoding enabled")
                        return merge_videos(video_paths, output_path, progress_callback, timeout, True)
                
                time.sleep(0.1)
        
        # Wait for process to complete
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg process timed out after {timeout} seconds")
            process.kill()
            stdout, stderr = process.communicate()
            return False
        
        # Clean up
        os.unlink(file_list_path)
        
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {stderr}")
            
            # If the process failed and we weren't re-encoding, try again with re-encoding
            if not force_reencode and "invalid dropping" in stderr:
                logger.info("Merge failed with stream copy, trying again with re-encoding")
                return merge_videos(video_paths, output_path, progress_callback, timeout, True)
            
            return False
        
        # Final progress update
        if progress_callback:
            progress_callback(100)
        
        logger.info(f"Videos merged successfully: {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"Error merging videos: {e}", exc_info=True)
        return False
