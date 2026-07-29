"use client";

import { Alert } from "antd";
import { ReactNode } from "react";

interface AntAlertProps {
  type: "success" | "info" | "warning" | "error";
  message: ReactNode;
  description?: ReactNode;
  closable?: boolean;
  className?: string;
  showIcon?: boolean;
}

export function AntAlert({
  type,
  message,
  description,
  closable,
  className = "",
  showIcon = true,
}: AntAlertProps) {
  return (
    <Alert
      type={type}
      title={message}
      description={description}
      closable={closable}
      showIcon={showIcon}
      className={className}
    />
  );
}
