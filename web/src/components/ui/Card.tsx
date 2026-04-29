import { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-surface-raised rounded-xl border border-gray-800 p-6 ${className}`}>
      {children}
    </div>
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-lg font-semibold mb-4">{children}</h3>;
}

export function CardStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <p className="text-sm text-gray-400">{label}</p>
      <p className={`text-2xl font-bold ${color || "text-white"}`}>{value}</p>
    </div>
  );
}
