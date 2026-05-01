"use client";

import { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  loading?: boolean;
  children: ReactNode;
  icon?: ReactNode;
}

export function Button({
  variant = "primary",
  loading,
  children,
  icon,
  className = "",
  ...props
}: ButtonProps) {
  const base = "inline-flex items-center justify-center gap-2 font-medium text-sm transition-all duration-200 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed";

  const variants = {
    primary: "btn-primary h-12 px-6",
    secondary: "btn-secondary h-12 px-6",
    ghost: "text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg px-4 py-2",
    danger: "bg-error/10 text-error border border-error/20 rounded-xl h-12 px-6 hover:bg-error/20",
  };

  return (
    <button
      className={`${base} ${variants[variant]} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? (
        <>
          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span>Loading...</span>
        </>
      ) : (
        <>
          {icon && <span className="w-4 h-4">{icon}</span>}
          {children}
        </>
      )}
    </button>
  );
}
