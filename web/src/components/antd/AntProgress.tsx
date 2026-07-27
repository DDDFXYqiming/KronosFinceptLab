"use client";

import { Progress, Steps } from "antd";
import { ReactNode } from "react";

interface AntProgressProps {
  percent: number;
  steps?: number;
  className?: string;
}

export function AntProgress({ percent, steps, className = "" }: AntProgressProps) {
  if (steps) {
    return <Steps current={Math.floor(percent / 100 * steps)} className={className} size="small" />;
  }
  return <Progress percent={Math.round(percent)} className={className} />;
}
