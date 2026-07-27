"use client";

import { ReactNode } from "react";
import { motion } from "framer-motion";
import { fadeInUp, viewportOnce } from "@/lib/animations";
import { Tag } from "antd";

interface SectionLabelProps {
  children: ReactNode;
  className?: string;
}

export function SectionLabel({ children, className = "" }: SectionLabelProps) {
  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      className={className}
    >
      <Tag color="blue" style={{ borderRadius: 12, padding: "2px 10px", fontSize: 12 }}>{children}</Tag>
    </motion.div>
  );
}
