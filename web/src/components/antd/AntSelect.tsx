"use client";

import { Select } from "antd";
import { useMemo } from "react";

interface AntSelectOption<T extends string> {
  value: T;
  label: string;
}

interface AntSelectProps<T extends string> {
  value: T;
  options: ReadonlyArray<AntSelectOption<T>>;
  onChange: (value: T) => void;
  ariaLabel: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  buttonClassName?: string;
  description?: string;
}

export function AntSelect<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className = "",
  disabled = false,
  placeholder,
}: AntSelectProps<T>) {
  const selectOptions = useMemo(
    () => options.map((opt) => ({ value: opt.value, label: opt.label })),
    [options]
  );

  return (
    <Select
      value={value}
      onChange={(v) => onChange(v as T)}
      options={selectOptions}
      placeholder={placeholder || ariaLabel}
      disabled={disabled}
      className={className}
      popupMatchSelectWidth={false}
      style={{ minHeight: 44 }}
    />
  );
}
