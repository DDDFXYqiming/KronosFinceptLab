"use client";

import { DatePicker } from "antd";
import dayjs from "dayjs";

interface AntDatePickerProps {
  value: string; // YYYYMMDD
  onChange: (value: string) => void;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
}

export function AntDatePicker({
  value,
  onChange,
  className = "",
  disabled,
  placeholder,
}: AntDatePickerProps) {
  const dayjsValue = value ? dayjs(value, "YYYYMMDD") : null;

  return (
    <DatePicker
      value={dayjsValue}
      onChange={(date) => {
        if (date) {
          onChange(date.format("YYYYMMDD"));
        }
      }}
      format="YYYY-MM-DD"
      disabled={disabled}
      className={className}
      placeholder={placeholder || "选择日期"}
      style={{ minHeight: 44, width: "100%" }}
    />
  );
}
