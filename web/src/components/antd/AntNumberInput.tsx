"use client";

import { InputNumber } from "antd";

interface AntNumberInputProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  className?: string;
  disabled?: boolean;
  ariaLabel?: string;
}

export function AntNumberInput({
  value,
  onChange,
  min = 0,
  max = 9999,
  step = 1,
  className = "",
  disabled,
  ariaLabel,
}: AntNumberInputProps) {
  return (
    <InputNumber
      value={value}
      onChange={(v) => onChange(v ?? 0)}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      className={className}
      aria-label={ariaLabel}
      style={{ minHeight: 44, width: "100%" }}
    />
  );
}
