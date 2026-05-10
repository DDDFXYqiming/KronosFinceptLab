"use client";

import { ReactNode } from "react";
import { motion } from "framer-motion";
import { fadeInUp, stagger, viewportOnce } from "@/lib/animations";

interface CardProps {
  children: ReactNode;
  className?: string;
  featured?: boolean;
  hoverable?: boolean;
  /** Index for stagger animation (0-based) */
  index?: number;
  /** Disable entrance animation */
  noAnimation?: boolean;
}

export function Card({
  children,
  className = "",
  featured = false,
  hoverable = false,
  index,
  noAnimation = false,
}: CardProps) {
  const content = (
    <div
      className={`
        min-w-0
        ${featured ? "card-featured" : "card"}
        ${hoverable ? "hover-lift" : ""}
        ${className}
      `}
    >
      {children}
    </div>
  );

  if (noAnimation) return content;

  return (
    <motion.div
      variants={fadeInUp}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      transition={{ delay: index != null ? index * 0.08 : 0 }}
    >
      {content}
    </motion.div>
  );
}

// ── Stagger container for card grids ──
export function CardGrid({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      className={className}
    >
      {children}
    </motion.div>
  );
}

interface CardTitleProps {
  children: ReactNode;
  subtitle?: string;
  action?: ReactNode;
}

export function CardTitle({ children, subtitle, action }: CardTitleProps) {
  return (
    <div className="mb-3 flex min-w-0 flex-col gap-2 sm:mb-4 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
      <div className="min-w-0">
        <h3 className="break-words text-base font-semibold text-foreground sm:text-lg">{children}</h3>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {action && <div className="w-full shrink-0 sm:w-auto">{action}</div>}
    </div>
  );
}

interface CardStatProps {
  label: string;
  value: string | number;
  color?: string;
  trend?: "up" | "down" | "neutral";
}

export function CardStat({ label, value, color, trend }: CardStatProps) {
  const trendColors = {
    up: "text-success",
    down: "text-error",
    neutral: "text-muted-foreground",
  };

  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={`break-words text-xl font-bold md:text-2xl ${color || trendColors[trend || "neutral"]}`}>
        {value}
      </p>
      {trend && trend !== "neutral" && (
        <p className={`mt-1 text-xs ${trendColors[trend]}`}>
          {trend === "up" ? "↑" : "↓"} Trending
        </p>
      )}
    </div>
  );
}
