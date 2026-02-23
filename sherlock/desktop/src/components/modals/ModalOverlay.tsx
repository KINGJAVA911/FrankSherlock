type Props = {
  children: React.ReactNode;
  className?: string;
  onBackdropClick?: () => void;
};

export default function ModalOverlay({ children, className, onBackdropClick }: Props) {
  return (
    <div
      className={`modal-overlay${className ? ` ${className}` : ""}`}
      role="dialog"
      aria-modal="true"
      onClick={onBackdropClick}
    >
      {children}
    </div>
  );
}
