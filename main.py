from mcp.server.fastmcp import FastMCP
import json
import os
import subprocess
from typing import List

# Initialize the MCP server
mcp = FastMCP("Media Manipulation Server")
MEDIA_DIR = "E:/project"

# Valid extensions for video and audio files
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']
AUDIO_EXTENSIONS = ['.aac', '.mp3', '.wav', '.ogg', '.flac', '.m4a']

# Resource to list available media files
@mcp.resource("directory://media")
def get_media_files() -> str:
    """Returns a JSON list of media files in the E:/project directory."""
    files = os.listdir(MEDIA_DIR)
    media_files = [f for f in files if f.lower().endswith(tuple(VIDEO_EXTENSIONS + AUDIO_EXTENSIONS))]
    return json.dumps(media_files)

# Resource to get metadata for a specific file
@mcp.resource("metadata://{filename}")
def get_metadata(filename: str) -> str:
    """Returns JSON metadata for the specified media file using ffprobe."""
    file_path = os.path.join(MEDIA_DIR, filename)
    if not os.path.exists(file_path):
        return json.dumps({"error": "File not found"})
    
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        file_path
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True)
        metadata = json.loads(result.stdout)
        return json.dumps(metadata)
    except subprocess.CalledProcessError as e:
        return json.dumps({"error": str(e)})

# Helper function to get audio codec of a file
def get_audio_codec(file_path: str) -> str:
    """Returns the audio codec of a media file using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        file_path
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True)
        metadata = json.loads(result.stdout)
        for stream in metadata.get("streams", []):
            if stream.get("codec_type") == "audio":
                return stream.get("codec_name", "unknown")
        return "none"
    except subprocess.CalledProcessError:
        return "error"

# Tool to trim video without re-encoding
@mcp.tool()
def trim_video(input_file: str, start_time: str, duration: str, output_file: str) -> str:
    """Trims a video file without re-encoding using FFmpeg. Ensures output is a video file."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if os.path.sep in input_file or os.path.sep in output_file:
        return "Error: File names cannot contain directory separators."
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    cmd = ["ffmpeg", "-ss", start_time, "-t", duration, "-i", input_path, "-c", "copy", output_path]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return f"Successfully trimmed video to {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error trimming video: {e.stderr}"

# Tool to concatenate videos without re-encoding
@mcp.tool()
def concatenate_videos(input_files: List[str], output_file: str) -> str:
    """Concatenates multiple video files without re-encoding using FFmpeg concat demuxer."""
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if os.path.sep in output_file:
        return "Error: Output file name cannot contain directory separators."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmpfile:
        for input_file in input_files:
            if os.path.sep in input_file:
                return "Error: Input file names cannot contain directory separators."
            input_path = os.path.join(MEDIA_DIR, input_file)
            if not os.path.exists(input_path):
                return f"Error: Input file {input_file} not found."
            tmpfile.write(f"file '{input_path}'\n")
        tmpfile_path = tmpfile.name
    
    cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", tmpfile_path,
        "-c", "copy",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.remove(tmpfile_path)
        return f"Successfully concatenated videos to {output_file}"
    except subprocess.CalledProcessError as e:
        os.remove(tmpfile_path)
        return f"Error concatenating videos: {e.stderr.decode()}"

# Tool to merge audio and video tracks
@mcp.tool()
def merge_audio_video(video_file: str, audio_file: str, output_file: str) -> str:
    """Merges a video file and an audio file into a single output file."""
    video_path = os.path.join(MEDIA_DIR, video_file)
    audio_path = os.path.join(MEDIA_DIR, audio_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if os.path.sep in video_file or os.path.sep in audio_file or os.path.sep in output_file:
        return "Error: File names cannot contain directory separators."
    if not os.path.exists(video_path):
        return f"Error: Video file {video_file} not found."
    if not os.path.exists(audio_path):
        return f"Error: Audio file {audio_file} not found."
    if not any(audio_file.lower().endswith(ext) for ext in AUDIO_EXTENSIONS):
        return f"Error: Audio file must have an audio extension ({', '.join(AUDIO_EXTENSIONS)})"
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    # Check audio codec compatibility
    audio_codec = get_audio_codec(audio_path)
    if audio_codec == "none":
        return "Error: Audio file has no audio stream."
    if audio_codec == "error":
        return "Error: Could not determine audio codec."
    if output_file.lower().endswith('.mp4') and audio_codec not in ['aac', 'mp3']:
        return f"Error: Audio codec {audio_codec} is not compatible with MP4 output. Use AAC or MP3."

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully merged audio and video to {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error merging audio and video: {e.stderr.decode()}"

# Tool to extract audio from video
@mcp.tool()
def extract_audio(video_file: str, output_audio_file: str) -> str:
    """Extracts audio from a video file. Re-encodes to MP3 if necessary."""
    video_path = os.path.join(MEDIA_DIR, video_file)
    output_path = os.path.join(MEDIA_DIR, output_audio_file)
    
    if os.path.sep in video_file or os.path.sep in output_audio_file:
        return "Error: File names cannot contain directory separators."
    if not os.path.exists(video_path):
        return f"Error: Video file {video_file} not found."
    if os.path.exists(output_path):
        return f"Error: Output file {output_audio_file} already exists."
    if not any(output_audio_file.lower().endswith(ext) for ext in AUDIO_EXTENSIONS):
        return f"Error: Output file must have an audio extension ({', '.join(AUDIO_EXTENSIONS)})"
    
    # Get audio codec of input video
    audio_codec = get_audio_codec(video_path)
    if audio_codec == "none":
        return "Error: Video file has no audio stream."
    if audio_codec == "error":
        return "Error: Could not determine audio codec."

    # Determine FFmpeg command based on output format and input codec
    if output_audio_file.lower().endswith('.mp3'):
        if audio_codec == 'mp3':
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vn",
                "-acodec", "copy",
                output_path
            ]
        else:
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-vn",
                "-acodec", "mp3",
                "-ab", "192k",
                output_path
            ]
    else:
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vn",
            "-acodec", "copy",
            output_path
        ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully extracted audio to {output_audio_file}"
    except subprocess.CalledProcessError as e:
        return f"Error extracting audio: {e.stderr.decode()}"

# Run the server
if __name__ == "__main__":
    mcp.run()