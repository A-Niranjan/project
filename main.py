from mcp.server.fastmcp import FastMCP
import json
import os
import subprocess
from typing import List, Dict, Any

# Initialize the MCP server
mcp = FastMCP("Media Manipulation Server")
MEDIA_DIR = "E:/project"

# Valid extensions for video, audio, and image files
VIDEO_EXTENSIONS = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']
AUDIO_EXTENSIONS = ['.aac', '.mp3', '.wav', '.ogg', '.flac', '.m4a']
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']

# Position mappings for overlay tool
POSITION_MAP = {
    "top-left": "10:10",
    "top-right": "main_w-overlay_w-10:10",
    "bottom-left": "10:main_h-overlay_h-10",
    "bottom-right": "main_w-overlay_w-10:main_h-overlay_h-10",
    "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2"
}

# Required parameters for each transformation type
TRANSFORM_PARAMS = {
    "crop": ["x", "y", "width", "height"],
    "scale": ["width", "height"],
    "rotate": ["angle"],
    "flip": ["direction"],
    "transpose": ["dir"],
    "pad": ["width", "height", "x", "y"]
}

# Resource to list available media files
@mcp.resource("directory://media")
def get_media_files() -> str:
    """Returns a JSON list of media files in the E:/project directory."""
    files = os.listdir(MEDIA_DIR)
    media_files = [f for f in files if f.lower().endswith(tuple(VIDEO_EXTENSIONS + AUDIO_EXTENSIONS + IMAGE_EXTENSIONS))]
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

    
# Helper function to get video duration for fade tool
def get_video_duration(file_path: str) -> float:
    """Returns the duration of a video file in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0

# Splitting Tool
@mcp.tool()
def split_video(input_file: str, segment_duration: float, output_pattern: str) -> str:
    """Splits a video into segments of specified duration using FFmpeg."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if segment_duration <= 0:
        return "Error: segment_duration must be positive."
    if os.path.sep in output_pattern:
        return "Error: Output pattern cannot contain directory separators."
    
    output_pattern_full = os.path.join(MEDIA_DIR, output_pattern)
    
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-f", "segment",
        "-segment_time", str(segment_duration),
        "-c", "copy",
        output_pattern_full
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully split video into segments using pattern {output_pattern}"
    except subprocess.CalledProcessError as e:
        return f"Error splitting video: {e.stderr.decode()}"

# Fade Tool
@mcp.tool()
def fade_video(input_file: str, fade_in_duration: float, fade_out_duration: float, output_file: str) -> str:
    """Applies fade-in and/or fade-out effects to video and audio using FFmpeg."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if fade_in_duration < 0 or fade_out_duration < 0:
        return "Error: Fade durations must be non-negative."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    duration = get_video_duration(input_path)
    if duration == 0.0:
        return "Error: Could not determine video duration."
    
    video_filters = []
    audio_filters = []
    
    if fade_in_duration > 0:
        video_filters.append(f"fade=t=in:st=0:d={fade_in_duration}")
        audio_filters.append(f"afade=t=in:st=0:d={fade_in_duration}")
    
    if fade_out_duration > 0:
        fade_out_start = max(duration - fade_out_duration, 0)
        video_filters.append(f"fade=t=out:st={fade_out_start}:d={fade_out_duration}")
        audio_filters.append(f"afade=t=out:st={fade_out_start}:d={fade_out_duration}")
    
    vf = ",".join(video_filters) if video_filters else None
    af = ",".join(audio_filters) if audio_filters else None
    
    cmd = ["ffmpeg", "-i", input_path]
    if vf:
        cmd += ["-vf", vf]
    if af:
        cmd += ["-af", af]
    cmd += ["-c:v", "libx264", "-c:a", "aac", output_path]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully applied fade to {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error applying fade: {e.stderr.decode()}"


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

# Tool: Convert image sequence to video
@mcp.tool()
def images_to_video(input_pattern: str, frame_rate: float, output_file: str) -> str:
    """Converts a sequence of images into a video using FFmpeg."""
    if not frame_rate > 0:
        return "Error: frame_rate must be positive"
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    if os.path.sep in output_file:
        return "Error: Output file name cannot contain directory separators."
    output_path = os.path.join(MEDIA_DIR, output_file)
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."

    input_pattern_full = os.path.join(MEDIA_DIR, input_pattern)

    cmd = [
        "ffmpeg",
        "-framerate", str(frame_rate),
        "-i", input_pattern_full,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully created video {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error creating video: {e.stderr.decode()}"

# Tool: Convert video to image sequence
@mcp.tool()
def video_to_images(input_file: str, output_pattern: str, frame_rate: float = None) -> str:
    """Converts a video into a sequence of images using FFmpeg."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if os.path.sep in output_pattern:
        return "Error: Output pattern cannot contain directory separators."
    if not (output_pattern.lower().endswith('.png') or output_pattern.lower().endswith('.jpg')):
        return "Error: Output pattern must end with .png or .jpg"

    output_pattern_full = os.path.join(MEDIA_DIR, output_pattern)

    cmd = ["ffmpeg", "-i", input_path]
    if frame_rate is not None:
        if frame_rate <= 0:
            return "Error: frame_rate must be positive"
        cmd += ["-vf", f"fps={frame_rate}"]
    cmd += [output_pattern_full]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully extracted images to {output_pattern}"
    except subprocess.CalledProcessError as e:
        return f"Error extracting images: {e.stderr.decode()}"

# Tool: Replace audio track in video
@mcp.tool()
def replace_audio_track(input_video: str, input_audio: str, output_file: str) -> str:
    """Replaces the audio track in a video file with a new audio file."""
    video_path = os.path.join(MEDIA_DIR, input_video)
    audio_path = os.path.join(MEDIA_DIR, input_audio)
    output_path = os.path.join(MEDIA_DIR, output_file)

    if not os.path.exists(video_path):
        return f"Error: Video file {input_video} not found."
    if not os.path.exists(audio_path):
        return f"Error: Audio file {input_audio} not found."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully replaced audio in {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error replacing audio: {e.stderr.decode()}"

# Tool: Overlay image on video (e.g., watermark)
@mcp.tool()
def overlay_image(input_video: str, input_image: str, position: str, output_file: str) -> str:
    """Overlays an image on a video at a specified position."""
    video_path = os.path.join(MEDIA_DIR, input_video)
    image_path = os.path.join(MEDIA_DIR, input_image)
    output_path = os.path.join(MEDIA_DIR, output_file)

    if not os.path.exists(video_path):
        return f"Error: Video file {input_video} not found."
    if not os.path.exists(image_path):
        return f"Error: Image file {input_image} not found."
    if position not in POSITION_MAP:
        return f"Error: Invalid position. Must be one of {list(POSITION_MAP.keys())}"
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"

    overlay_expr = POSITION_MAP[position]
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", image_path,
        "-filter_complex", f"[0:v][1:v]overlay={overlay_expr}[v]",
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully overlaid image on {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error overlaying image: {e.stderr.decode()}"

# Tool: Transform video (crop, scale, rotate, flip, transpose)
# Updated transform_video tool
@mcp.tool()
def transform_video(input_file: str, transformation: str, params: Dict[str, Any], output_file: str) -> str:
    """Applies a transformation (crop, scale, rotate, flip, transpose, pad) to a video."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    output_path = os.path.join(MEDIA_DIR, output_file)

    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if transformation not in TRANSFORM_PARAMS:
        return f"Error: Invalid transformation. Must be one of {list(TRANSFORM_PARAMS.keys())}"
    required_params = TRANSFORM_PARAMS[transformation]
    if not all(p in params for p in required_params):
        return f"Error: Missing parameters for {transformation}. Required: {required_params}"
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"

    if transformation == "crop":
        filter_str = "crop={width}:{height}:{x}:{y}".format(**params)
    elif transformation == "scale":
        filter_str = "scale={width}:{height}".format(**params)
    elif transformation == "rotate":
        filter_str = "rotate={angle}*PI/180".format(**params)
    elif transformation == "flip":
        direction = params["direction"]
        if direction not in ["horizontal", "vertical"]:
            return "Error: direction must be 'horizontal' or 'vertical'"
        filter_str = "hflip" if direction == "horizontal" else "vflip"
    elif transformation == "transpose":
        dir = params["dir"]
        if not 0 <= dir <= 3:
            return "Error: dir must be between 0 and 3"
        filter_str = "transpose={dir}".format(**params)
    elif transformation == "pad":
        color = params.get("color", "black")
        filter_str = "pad={width}:{height}:{x}:{y}:{color}".format(**params)

    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", filter_str,
        "-c:a", "copy",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully transformed video to {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error transforming video: {e.stderr.decode()}"

import math

@mcp.tool()
def apply_color_curves(input_file: str, red_curve: str, green_curve: str, blue_curve: str, output_file: str) -> str:
    """Apply advanced color curve adjustments with contrast, saturation, and vignette for a realistic vintage look."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    # Define the advanced curves filter
    curves_filter = f"curves=red='{red_curve}':green='{green_curve}':blue='{blue_curve}'"
    
    # Additional filters for realism
    eq_filter = "eq=contrast=1.2:saturation=0.8"
    
    # Compute vignette angle (pi/4 radians ≈ 0.7854)
    vignette_angle = math.pi / 4
    vignette_filter = f"vignette=angle={vignette_angle}"
    
    # Combine all filters
    filter_str = ",".join([curves_filter, eq_filter, vignette_filter])
    
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", filter_str,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "copy",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully applied color curves to {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error applying color curves: {e.stderr.decode()}"

@mcp.tool()
def set_video_fps(input_file: str, fps: float, output_file: str) -> str:
    """Set a custom frame rate for a vintage effect."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if fps <= 0:
        return "Error: fps must be positive."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    filter_str = f"fps=fps={fps}"
    
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", filter_str,
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully set fps to {fps} in {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error setting fps: {e.stderr.decode()}"

@mcp.tool()
def add_video_noise(input_file: str, noise_strength: int, noise_flags: str, output_file: str) -> str:
    """Add noise to a video for a vintage effect."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if noise_strength < 0:
        return "Error: noise_strength must be non-negative."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    filter_str = f"noise=c0s={noise_strength}:c0f={noise_flags}"
    
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-vf", filter_str,
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully added noise to {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error adding noise: {e.stderr.decode()}"

@mcp.tool()
def apply_overlay(input_file: str, overlay_file: str, position: str, opacity: float, output_file: str) -> str:
    """Apply an overlay video/image with position and opacity for a vintage effect."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    overlay_path = os.path.join(MEDIA_DIR, overlay_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if not os.path.exists(overlay_path):
        return f"Error: Overlay file {overlay_file} not found."
    if position not in POSITION_MAP:
        return f"Error: Invalid position. Must be one of {list(POSITION_MAP.keys())}"
    if not 0 <= opacity <= 1:
        return "Error: opacity must be between 0 and 1."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    overlay_expr = POSITION_MAP[position]
    filter_complex = (
        f"[1:v]format=yuva444p,colorchannelmixer=aa={opacity}[overlay];"
        f"[0:v][overlay]overlay={overlay_expr}[v]"
    )
    
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-i", overlay_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-c:a", "copy",
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return f"Successfully applied overlay to {output_file}"
    except subprocess.CalledProcessError as e:
        return f"Error applying overlay: {e.stderr.decode()}"


# Tool to apply a filter template (without overlay)
@mcp.tool()
def apply_filter_template(input_file: str, template_name: str, output_file: str) -> str:
    """Apply a predefined filter template to a video."""
    input_path = os.path.join(MEDIA_DIR, input_file)
    output_path = os.path.join(MEDIA_DIR, output_file)
    template_path = os.path.join(MEDIA_DIR, "filters", f"{template_name}.json")
    
    # Validation checks
    if not os.path.exists(input_path):
        return f"Error: Input file {input_file} not found."
    if not os.path.exists(template_path):
        return f"Error: Filter template {template_name} not found."
    if os.path.exists(output_path):
        return f"Error: Output file {output_file} already exists."
    if not any(output_file.lower().endswith(ext) for ext in VIDEO_EXTENSIONS):
        return f"Error: Output file must have a video extension ({', '.join(VIDEO_EXTENSIONS)})"
    
    with open(template_path, "r") as f:
        template = json.load(f)
    
    current_file = input_file
    temp_files = []
    
    # Apply curves, eq, and vignette in one step
    if "curves" in template and "eq" in template and "vignette" in template:
        curves = template["curves"]
        eq = template["eq"]
        vignette = template["vignette"]
        
        curves_filter = f"curves=red='{curves['red']}':green='{curves['green']}':blue='{curves['blue']}'"
        eq_filter = f"eq=contrast={eq['contrast']}:saturation={eq['saturation']}"
        vignette_filter = f"vignette=angle={vignette['angle']}"
        filter_str = ",".join([curves_filter, eq_filter, vignette_filter])
        
        temp_output = f"temp_{len(temp_files)}.mp4"
        temp_files.append(temp_output)
        cmd = [
            "ffmpeg", "-i", os.path.join(MEDIA_DIR, current_file),
            "-vf", filter_str, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy",
            os.path.join(MEDIA_DIR, temp_output)
        ]
        subprocess.run(cmd, check=True)
        current_file = temp_output
    
    # Apply fps
    if "fps" in template:
        fps = template["fps"]
        temp_output = f"temp_{len(temp_files)}.mp4"
        temp_files.append(temp_output)
        cmd = [
            "ffmpeg", "-i", os.path.join(MEDIA_DIR, current_file),
            "-vf", f"fps=fps={fps}", "-c:v", "libx264", "-c:a", "copy",
            os.path.join(MEDIA_DIR, temp_output)
        ]
        subprocess.run(cmd, check=True)
        current_file = temp_output
    
    # Apply noise
    if "noise" in template:
        noise = template["noise"]
        filter_str = f"noise=c0s={noise['strength']}:c0f={noise['flags']}"
        temp_output = f"temp_{len(temp_files)}.mp4"
        temp_files.append(temp_output)
        cmd = [
            "ffmpeg", "-i", os.path.join(MEDIA_DIR, current_file),
            "-vf", filter_str, "-c:v", "libx264", "-c:a", "copy",
            os.path.join(MEDIA_DIR, temp_output)
        ]
        subprocess.run(cmd, check=True)
        current_file = temp_output
    
    # Rename the final temp file to the output file
    os.rename(os.path.join(MEDIA_DIR, current_file), output_path)
    
    # Clean up temporary files
    for temp_file in temp_files:
        if os.path.exists(os.path.join(MEDIA_DIR, temp_file)):
            os.remove(os.path.join(MEDIA_DIR, temp_file))
    
    return f"Successfully applied {template_name} filter to {output_file}"

# Tool to list available filters
@mcp.tool()
def list_filter_templates() -> str:
    """List available filter templates."""
    filters_dir = os.path.join(MEDIA_DIR, "filters")
    if not os.path.exists(filters_dir):
        return "No filter templates found."
    
    templates = [f.split(".")[0] for f in os.listdir(filters_dir) if f.endswith(".json")]
    return json.dumps(templates)

# Run the server
if __name__ == "__main__":
    mcp.run()