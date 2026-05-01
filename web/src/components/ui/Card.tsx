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
    <div className="flex items-start justify-between mb-4">
      <div>
        <h3 className="text-lg font-semibold text-foreground">{children}</h3>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {action && <div>{action}</div>}
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
      <p className={`text-2xl font-bold ${color || trendColors[trend || "neutral"]}`}>
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
