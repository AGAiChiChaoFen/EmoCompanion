import imageio
import os


class VideoWriterByImageIO:
    """
    视频写出封装。

    负责统一写盘参数、目录创建和帧格式转换。
    """

    def __init__(self, video_path, fps=25, **kwargs):
        # 读取写盘参数并设置默认值。
        video_format = kwargs.get("format", "mp4")  # 容器格式。
        codec = kwargs.get("vcodec", "libx264")  # 编码器。
        quality = kwargs.get("quality")  # 输出质量。
        pixelformat = kwargs.get("pixelformat", "yuv420p")  # 像素格式。
        macro_block_size = kwargs.get("macro_block_size", 2)
        ffmpeg_params = ["-crf", str(kwargs.get("crf", 18))]

        output_dir = os.path.dirname(video_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        writer = imageio.get_writer(
            video_path,
            fps=fps,
            format=video_format,
            codec=codec,
            quality=quality,
            ffmpeg_params=ffmpeg_params,
            pixelformat=pixelformat,
            macro_block_size=macro_block_size,
        )
        self.writer = writer

    def __call__(self, img, fmt="bgr"):
        """
        写入单帧图像。

        当输入为 BGR 时先转换到写盘所需通道顺序。
        """

        if fmt == "bgr":
            frame = img[..., ::-1]
        else:
            frame = img
        self.writer.append_data(frame)

    def close(self):
        """
        关闭写盘器并落盘缓冲。
        """

        self.writer.close()
