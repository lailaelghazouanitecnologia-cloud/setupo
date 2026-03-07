"use client";

import { useState, useCallback, useRef } from "react";
import {
  validate, validateField, getFieldError,
  type ValidationSchema, type ValidationResult, type FieldValidator,
} from "@/lib/validators";

// ══════════════════════════════════════════════════════════════
//  useFormManager — Form state, validation, and submission
// ══════════════════════════════════════════════════════════════

interface UseFormManagerOptions<T extends Record<string, unknown>> {
  initial: T;
  schema?: ValidationSchema;
  onSubmit: (values: T) => Promise<void>;
}

interface FormManager<T extends Record<string, unknown>> {
  values: T;
  errors: Record<string, string>;
  touched: Record<string, boolean>;
  submitting: boolean;
  submitError: string | null;
  submitted: boolean;

  /** Set a single field value */
  setValue: <K extends keyof T>(field: K, value: T[K]) => void;
  /** Set multiple values at once */
  setValues: (partial: Partial<T>) => void;
  /** Mark a field as touched (triggers inline validation) */
  touch: (field: string) => void;
  /** Get error for a specific field (only if touched) */
  fieldError: (field: string) => string | undefined;
  /** Validate all fields and return result */
  validateAll: () => ValidationResult;
  /** Submit the form (validates first) */
  submit: () => Promise<void>;
  /** Reset to initial state */
  reset: () => void;
  /** Is the form valid right now? (without showing errors) */
  isValid: boolean;
  /** Create onChange handler for an input */
  onChange: (field: keyof T) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
  /** Create onBlur handler for an input */
  onBlur: (field: string) => () => void;
}

export function useFormManager<T extends Record<string, unknown>>(options: UseFormManagerOptions<T>): FormManager<T> {
  const { initial, schema, onSubmit } = options;

  const [values, setValues] = useState<T>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const schemaRef = useRef(schema);
  schemaRef.current = schema;

  const setValue = useCallback(<K extends keyof T>(field: K, value: T[K]) => {
    setValues((v) => ({ ...v, [field]: value }));
    // Clear field error on change
    setErrors((e) => {
      if (e[field as string]) {
        const next = { ...e };
        delete next[field as string];
        return next;
      }
      return e;
    });
  }, []);

  const setValuesPartial = useCallback((partial: Partial<T>) => {
    setValues((v) => ({ ...v, ...partial }));
  }, []);

  const touch = useCallback((field: string) => {
    setTouched((t) => ({ ...t, [field]: true }));
    // Run inline validation for this field
    if (schemaRef.current?.fields?.[field]) {
      const err = validateField(field, (values as Record<string, unknown>)[field], schemaRef.current.fields[field]);
      if (err) {
        setErrors((e) => ({ ...e, [field]: err.message }));
      } else {
        setErrors((e) => {
          if (e[field]) {
            const next = { ...e };
            delete next[field];
            return next;
          }
          return e;
        });
      }
    }
  }, [values]);

  const fieldError = useCallback((field: string): string | undefined => {
    if (!touched[field]) return undefined;
    return errors[field];
  }, [touched, errors]);

  const validateAll = useCallback((): ValidationResult => {
    if (!schemaRef.current) return { valid: true, errors: [] };
    const result = validate(schemaRef.current, values as Record<string, unknown>);
    // Convert to error map
    const errorMap: Record<string, string> = {};
    for (const e of result.errors) {
      if (!errorMap[e.field]) errorMap[e.field] = e.message;
    }
    setErrors(errorMap);
    // Mark all fields as touched
    const allTouched: Record<string, boolean> = {};
    if (schemaRef.current.fields) {
      for (const field of Object.keys(schemaRef.current.fields)) {
        allTouched[field] = true;
      }
    }
    setTouched((t) => ({ ...t, ...allTouched }));
    return result;
  }, [values]);

  const submit = useCallback(async () => {
    setSubmitError(null);
    const result = validateAll();
    if (!result.valid) return;

    setSubmitting(true);
    try {
      await onSubmit(values);
      setSubmitted(true);
    } catch (err: any) {
      setSubmitError(err.message || "An error occurred");
    }
    setSubmitting(false);
  }, [values, validateAll, onSubmit]);

  const reset = useCallback(() => {
    setValues(initial);
    setErrors({});
    setTouched({});
    setSubmitting(false);
    setSubmitError(null);
    setSubmitted(false);
  }, [initial]);

  const isValid = !schemaRef.current || validate(schemaRef.current, values as Record<string, unknown>).valid;

  const onChange = useCallback((field: keyof T) => {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const val = e.target.type === "number" ? Number(e.target.value) : e.target.value;
      setValue(field, val as T[keyof T]);
    };
  }, [setValue]);

  const onBlur = useCallback((field: string) => {
    return () => touch(field);
  }, [touch]);

  return {
    values,
    errors,
    touched,
    submitting,
    submitError,
    submitted,
    setValue,
    setValues: setValuesPartial,
    touch,
    fieldError,
    validateAll,
    submit,
    reset,
    isValid,
    onChange,
    onBlur,
  };
}
