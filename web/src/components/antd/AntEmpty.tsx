"use client";

import { Empty } from "antd";

interface AntEmptyProps {
  description?: string;
  image?: React.ReactNode;
}

export function AntEmpty({ description = "暂无数据", image }: AntEmptyProps) {
  return <Empty description={description} image={image} />;
}
