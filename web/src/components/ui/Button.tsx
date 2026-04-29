"use client";

import { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  loading?: boolean;
  children: ReactNode;
}

export function Button({ variant = "primary", loading, children, className = "", ...props }: ButtonProps) {
  const base = "px-4 py-2 rounded-lg font-medium text-sm transition-all disabled:opacity-50";
  const variants = {
    primary: "bg-gradient-primary text-white hover:opacity-90",
    secondary: "bg-surface-overlay text-gray-200 hover:bg-gray-700",
    ghost: "text-gray-400 hover:text-white hover:bg-surface-overlay",
  };

  return (
    <button className={`${base} ${variants[variant]} ${className}`} disabled={loading} {...props}>
      {loading ? "⏳ Loading..." : children}
    </button>
  );
}
