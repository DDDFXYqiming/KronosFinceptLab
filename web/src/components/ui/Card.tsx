import { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  featured?: boolean;
  hoverable?: boolean;
}

export function Card({ children, className = "", featured = false, hoverable = false }: CardProps) {
  return (
    <div
      className={`
        ${featured ? "card-featured" : "card"}
        ${hoverable ? "hover-lift" : ""}
        min-w-0
        ${className}
      `}
    >
      {children}
    </div>
  );
}

interface CardTitleProps {
  children: ReactNode;
  subtitle?: string;
  action?: ReactNode;
}

export function CardTitle({ children, subtitle, action }: CardTitleProps) {
  return (
    <div className="mb-4 flex min-w-0 items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="text-lg font-semibold text-foreground">{children}</h3>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
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
        <p className={`text-xs mt-1 ${trendColors[trend]}`}>
          {trend === "up" ? "↑" : "↓"} Trending
        </p>
      )}
    </div>
  );
}
