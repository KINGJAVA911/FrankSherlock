import { getCurrentWindow } from "@tauri-apps/api/window";
import "./Titlebar.css";

const appWindow = getCurrentWindow();

type Props = {
  onClose: () => void;
};

export default function Titlebar({ onClose }: Props) {
  return (
    <div className="titlebar" data-tauri-drag-region>
      <span>Frank Sherlock</span>
      <div className="titlebar-controls">
        <button type="button" onClick={() => appWindow.minimize()} aria-label="Minimize">&#x2500;</button>
        <button type="button" onClick={() => appWindow.toggleMaximize()} aria-label="Maximize">&#x25A1;</button>
        <button type="button" className="close" onClick={onClose} aria-label="Close">&#x2715;</button>
      </div>
    </div>
  );
}
