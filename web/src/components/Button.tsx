import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
}

/** The only button in the application. No shadow, radius capped at 2px, a border colour change on hover. */
export function Button({ variant = "primary", className, type = "button", ...rest }: ButtonProps) {
  const variantClass = variant === "secondary" ? "button--secondary" : "button--primary";
  const combined = className ? `button ${variantClass} ${className}` : `button ${variantClass}`;
  return <button type={type} className={combined} {...rest} />;
}
