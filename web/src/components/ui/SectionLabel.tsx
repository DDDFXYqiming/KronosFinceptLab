"use client";

import { ReactNode } from "react";
import { motion } from "framer-motion";
import { fadeInUp, viewportOnce } from "@/lib/animations";

interface SectionLabelProps {
  children: ReactNode;
  className?: string;
}

/** Accent-dotted pill badge for section headers (Minimalist Modern). */
export function SectionLabel({ children, className = "" }: SectionLabelProps) {
  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      className={`section-label ${className}`}
    >
      {children}
    </motion.div>
  );
}
