"use client";

import { Button as AntdButton } from "antd";
import { ReactNode } from "react";

interface AntButtonProps {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  loading?: boolean;
  disabled?: boolean;
  children: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
  className?: string;
  type?: "button" | "submit" | "reset";
  htmlType?: "button" | "submit" | "reset";
  href?: string;
  title?: string;
}

const variantMap: Record<string, "primary" | "default" | "text" | "dashed" | "link"> = {
  primary: "primary",
  secondary: "default",
  ghost: "text",
  danger: "primary",
};

export function AntButton({
  variant = "primary",
  loading,
  disabled,
  children,
  icon,
  onClick,
  className = "",
  type,
  htmlType,
  href,
}: AntButtonProps) {
  if (href) {
    return (
      <AntdButton
        type={variantMap[variant] || "default"}
        loading={loading}
        disabled={disabled}
        icon={icon}
        className={className}
        href={href}
      >
        {children}
      </AntdButton>
    );
  }

  return (
    <AntdButton
      type={variantMap[variant] || "default"}
      loading={loading}
      disabled={disabled}
      icon={icon}
      onClick={onClick}
      className={className}
      htmlType={htmlType || type}
      danger={variant === "danger"}
    >
      {children}
    </AntdButton>
  );
}
