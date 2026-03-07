"use client";

import { useState, useCallback, useRef } from "react";
import {
  validate, validateField,
  type ValidationSchema, type ValidationResult, type FieldValidator,
} from "@/lib/validators";

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
  setValue: <K extends keyof T>(field: K, value: T[K]) => void;
  setValues: (partial: Partial<T>) => void;
  touch: (field: string) => void;
  fieldError: (field: string) => string | undefined;
  validateAll: () => ValidationResult;
  submit: () => Promise<void>;
  reset: () => void;
  isValid: boolean;
  onChange: (field: keyof T) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
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
    const errorMap: Record<string, string> = {};
    for (const e of result.errors) {
      if (!errorMap[e.field]) errorMap[e.field] = e.message;
    }
    setErrors(errorMap);
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
    values, errors, touched, submitting, submitError, submitted,
    setValue, setValues: setValuesPartial, touch, fieldError,
    validateAll, submit, reset, isValid, onChange, onBlur,
  };
}
