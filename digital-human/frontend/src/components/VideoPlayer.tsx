/** 视频播放组件 - 使用 Canvas 渲染，提供更好的性能和流畅度 */
import { useEffect, useRef, useState, useCallback } from "react";

interface VideoPlayerProps {
  lastFrame: string | null;
  frameCount: number;
}

export function VideoPlayer({ lastFrame, frameCount }: VideoPlayerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Handle fullscreen change events
  useEffect(() => {
    const handleFullscreenChange = () => {
      const isCurrentlyFullscreen = !!(
        document.fullscreenElement ||
        (document as any).webkitFullscreenElement ||
        (document as any).mozFullScreenElement ||
        (document as any).msFullscreenElement
      );
      setIsFullscreen(isCurrentlyFullscreen);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    document.addEventListener("webkitfullscreenchange", handleFullscreenChange);
    document.addEventListener("mozfullscreenchange", handleFullscreenChange);
    document.addEventListener("MSFullscreenChange", handleFullscreenChange);

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      document.removeEventListener("webkitfullscreenchange", handleFullscreenChange);
      document.removeEventListener("mozfullscreenchange", handleFullscreenChange);
      document.removeEventListener("MSFullscreenChange", handleFullscreenChange);
    };
  }, []);

  // Toggle fullscreen
  const toggleFullscreen = useCallback(async () => {
    const container = containerRef.current;
    if (!container) return;

    try {
      if (
        document.fullscreenElement ||
        (document as any).webkitFullscreenElement ||
        (document as any).mozFullScreenElement ||
        (document as any).msFullscreenElement
      ) {
        // Exit fullscreen
        if (document.exitFullscreen) {
          await document.exitFullscreen();
        } else if ((document as any).webkitExitFullscreen) {
          await (document as any).webkitExitFullscreen();
        } else if ((document as any).mozCancelFullScreen) {
          await (document as any).mozCancelFullScreen();
        } else if ((document as any).msExitFullscreen) {
          await (document as any).msExitFullscreen();
        }
      } else {
        // Enter fullscreen
        if (container.requestFullscreen) {
          await container.requestFullscreen();
        } else if ((container as any).webkitRequestFullscreen) {
          await (container as any).webkitRequestFullscreen();
        } else if ((container as any).mozRequestFullScreen) {
          await (container as any).mozRequestFullScreen();
        } else if ((container as any).msRequestFullscreen) {
          await (container as any).msRequestFullscreen();
        }
      }
    } catch (error) {
      console.error("全屏操作失败:", error);
    }
  }, []);

  // Render frame to Canvas
  useEffect(() => {
    if (!lastFrame) return;

    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;

    // Load image and draw to canvas
    const imgSrc = lastFrame.startsWith("data:") ? lastFrame : `data:image/jpeg;base64,${lastFrame}`;
    
    // Use onload to ensure image is loaded before drawing
    const handleLoad = () => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Set canvas size to match image (only if changed)
      const imgWidth = img.naturalWidth || img.width;
      const imgHeight = img.naturalHeight || img.height;
      
      if (canvas.width !== imgWidth || canvas.height !== imgHeight) {
        canvas.width = imgWidth;
        canvas.height = imgHeight;
      }

      // Clear and draw
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    };

    // Remove previous listener to avoid multiple calls
    img.onload = null;
    img.onload = handleLoad;
    
    // Only set src if it's different to avoid unnecessary reloads
    if (img.src !== imgSrc) {
      img.src = imgSrc;
    } else {
      // If src is the same, trigger load manually
      handleLoad();
    }
  }, [lastFrame]);

  return (
    <div className="video-player">
      {frameCount > 0 ? (
        <div className="video-container">
          <div className="video-info">
            已接收 {frameCount} 个视频帧 (Canvas 渲染)
            <button
              className="fullscreen-button"
              onClick={toggleFullscreen}
              title={isFullscreen ? "退出全屏" : "全屏显示"}
            >
              {isFullscreen ? "退出全屏" : "全屏"}
            </button>
          </div>
          <div
            ref={containerRef}
            className="video-frame-container"
            style={{ 
              width: '100%', 
              backgroundColor: '#000',
              minHeight: '300px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              position: 'relative'
            }}
          >
            <canvas
              ref={canvasRef}
              style={{
                maxWidth: '100%',
                maxHeight: '100%',
                objectFit: 'contain'
              }}
            />
            <img
              ref={imgRef}
              alt=""
              style={{ display: 'none' }}
            />
          </div>
        </div>
      ) : (
        <div className="video-placeholder">
          <div className="placeholder-text">等待视频流...</div>
        </div>
      )}
    </div>
  );
}
