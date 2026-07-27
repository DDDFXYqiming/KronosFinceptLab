"use client";

import { Modal } from "antd";
import { ReactNode } from "react";

interface AntModalProps {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

export function AntModal({ open, onClose, title, children, footer, width }: AntModalProps) {
  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={title}
      footer={footer}
      width={width}
      destroyOnClose
    >
      {children}
    </Modal>
  );
}
