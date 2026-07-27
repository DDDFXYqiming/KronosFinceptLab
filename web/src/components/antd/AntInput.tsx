"use client";

import { Input } from "antd";
import type { KeyboardEvent, ReactNode } from "react";

interface AntInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  type?: string;
  id?: string;
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void;
  autoComplete?: string;
  prefix?: ReactNode;
  suffix?: ReactNode;
}

export function AntInput({
  value,
  onChange,
  placeholder,
  className = "",
  disabled,
  type,
  id,
  onKeyDown,
  autoComplete,
  prefix,
  suffix,
}: AntInputProps) {
  if (type === "password") {
    return (
      <Input.Password
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={className}
        id={id}
        autoComplete={autoComplete}
        prefix={prefix}
        style={{ minHeight: 44 }}
      />
    );
  }

  return (
    <Input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={className}
      id={id}
      onKeyDown={onKeyDown}
      autoComplete={autoComplete}
      prefix={prefix}
      suffix={suffix}
      style={{ minHeight: 44 }}
    />
  );
}
