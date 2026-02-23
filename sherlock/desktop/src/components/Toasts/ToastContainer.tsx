import "./ToastContainer.css";

type Props = {
  notice: string | null;
  error: string | null;
};

export default function ToastContainer({ notice, error }: Props) {
  return (
    <div className="toast-container">
      {notice && <div className="toast notice">{notice}</div>}
      {error && <div className="toast error">{error}</div>}
    </div>
  );
}
