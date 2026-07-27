"use client";

import { Input } from "antd";

interface AntInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export function AntInput({ value, onChange, placeholder, className = "", disabled }: AntInputProps) {
  return (
    <Input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={className}
      style={{ minHeight: 44 }}
    />
  );
}
