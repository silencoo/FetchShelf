export type VideoSnapshot = Promise<{ file: File; error?: never } | { file?: never; error: string }>;

/** Copy pixels synchronously on the Share tap; only PNG encoding is deferred. */
export function captureVideoSnapshot(video: HTMLVideoElement | null): VideoSnapshot {
  const canvas = document.createElement("canvas");
  try {
    if (!video || video.readyState < 2 || video.seeking || !video.videoWidth || !video.videoHeight) {
      throw new Error("当前画面尚未准备好，请等视频显示后重新打开分享。");
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("此浏览器无法截取视频画面。");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const name = `frame-${Math.round(video.currentTime * 1000)}ms-${Date.now()}.png`;
    return new Promise((resolve) => {
      try {
        canvas.toBlob((blob) => {
          canvas.width = canvas.height = 0;
          resolve(blob?.size
            ? { file: new File([blob], name, { type: "image/png" }) }
            : { error: "截图生成失败，请重新打开分享。" });
        }, "image/png");
      } catch {
        canvas.width = canvas.height = 0;
        resolve({ error: "无法读取当前视频画面，请重新打开分享。" });
      }
    });
  } catch (error) {
    canvas.width = canvas.height = 0;
    return Promise.resolve({ error: error instanceof Error && error.name !== "SecurityError"
      ? error.message : "无法读取当前视频画面，请重新打开分享。" });
  }
}
