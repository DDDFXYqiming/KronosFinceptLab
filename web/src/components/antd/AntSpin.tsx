"use client";

import { Spin } from "antd";
import { ReactNode } from "react";

interface AntSpinProps {
  spinning?: boolean;
  children?: ReactNode;
  tip?: string;
}

export function AntSpin({ spinning = true, children, tip }: AntSpinProps) {
  return <Spin spinning={spinning} tip={tip}>{children}</Spin>;
}
