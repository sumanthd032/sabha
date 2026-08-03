import { useId } from "react";
import type { InputHTMLAttributes } from "react";

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

/** A labelled input with an optional error message, per the quality floor in section 5.7. */
export function Field({ label, error, id, className, ...rest }: FieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = error ? `${inputId}-error` : undefined;
  const wrapperClass = error ? "field field--error" : "field";
  return (
    <div className={className ? `${wrapperClass} ${className}` : wrapperClass}>
      <label className="field__label" htmlFor={inputId}>
        {label}
      </label>
      <input
        id={inputId}
        className="field__input"
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        {...rest}
      />
      {error ? (
        <span id={errorId} className="error-note__body">
          {error}
        </span>
      ) : null}
    </div>
  );
}
