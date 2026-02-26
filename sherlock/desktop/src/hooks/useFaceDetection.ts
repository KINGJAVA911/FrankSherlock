import { useEffect, useState } from "react";
import { cancelFaceDetect, detectFaces, getFaceDetectStatus } from "../api";
import type { FaceDetectProgress, RootInfo } from "../types";
import { errorMessage } from "../utils";

type FaceDetectionCallbacks = {
  pollMs: number;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

export function useFaceDetection({ pollMs, onNotice, onError }: FaceDetectionCallbacks) {
  const [facesMode, setFacesMode] = useState(false);
  const [faceProgress, setFaceProgress] = useState<FaceDetectProgress | null>(null);

  // Poll face detection progress
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const status = await getFaceDetectStatus();
        setFaceProgress(status);
      } catch { /* ignore */ }
    }, pollMs);
    return () => clearInterval(id);
  }, [pollMs]);

  async function onDetectFaces(root: RootInfo) {
    try {
      await detectFaces(root.id);
      onNotice(`Face detection started for "${root.rootName}"`);
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  async function onCancelFaceDetect() {
    try {
      await cancelFaceDetect();
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  return {
    facesMode,
    setFacesMode,
    faceProgress,
    onDetectFaces,
    onCancelFaceDetect,
  };
}
