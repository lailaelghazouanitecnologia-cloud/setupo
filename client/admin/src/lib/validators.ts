// ══════════════════════════════════════════════════════════════
//  Admin Validation System — Cascading Field → Group → Form
// ══════════════════════════════════════════════════════════════

// ── Types ──────────────────────────────────────────────────

export interface ValidationError {
  field: string;
  message: string;
  code: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
}

export type FieldValidator = (value: unknown, field: string) => ValidationError | null;
export type GroupValidator = (values: Record<string, unknown>) => ValidationError[];

// ── Field Validators (Tier 1) ─────────────────────────────

export function required(msg?: string): FieldValidator {
  return (value, field) => {
    const v = typeof value === "string" ? value.trim() : value;
    if (v === null || v === undefined || v === "") {
      return { field, message: msg || `${field} is required`, code: "required" };
    }
    return null;
  };
}

export function minLength(min: number, msg?: string): FieldValidator {
  return (value, field) => {
    if (typeof value !== "string") return null;
    if (value.trim().length < min) {
      return { field, message: msg || `${field} must be at least ${min} characters`, code: "min_length" };
    }
    return null;
  };
}

export function maxLength(max: number, msg?: string): FieldValidator {
  return (value, field) => {
    if (typeof value !== "string") return null;
    if (value.length > max) {
      return { field, message: msg || `${field} must be at most ${max} characters`, code: "max_length" };
    }
    return null;
  };
}

export function email(msg?: string): FieldValidator {
  return (value, field) => {
    if (typeof value !== "string" || !value) return null;
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
      return { field, message: msg || "Invalid email address", code: "email" };
    }
    return null;
  };
}

export function pattern(regex: RegExp, msg?: string): FieldValidator {
  return (value, field) => {
    if (typeof value !== "string" || !value) return null;
    if (!regex.test(value)) {
      return { field, message: msg || `${field} format is invalid`, code: "pattern" };
    }
    return null;
  };
}

export function minValue(min: number, msg?: string): FieldValidator {
  return (value, field) => {
    const n = typeof value === "string" ? parseFloat(value) : (value as number);
    if (isNaN(n)) return null;
    if (n < min) {
      return { field, message: msg || `${field} must be at least ${min}`, code: "min_value" };
    }
    return null;
  };
}

export function maxValue(max: number, msg?: string): FieldValidator {
  return (value, field) => {
    const n = typeof value === "string" ? parseFloat(value) : (value as number);
    if (isNaN(n)) return null;
    if (n > max) {
      return { field, message: msg || `${field} must be at most ${max}`, code: "max_value" };
    }
    return null;
  };
}

// ── Group Validators (Tier 2) ─────────────────────────────

export function fieldsMatch(fieldA: string, fieldB: string, msg?: string): GroupValidator {
  return (values) => {
    if (values[fieldA] !== values[fieldB]) {
      return [{ field: fieldB, message: msg || `${fieldB} must match ${fieldA}`, code: "fields_match" }];
    }
    return [];
  };
}

export function atLeastOne(fields: string[], msg?: string): GroupValidator {
  return (values) => {
    const hasValue = fields.some((f) => {
      const v = values[f];
      return v !== null && v !== undefined && v !== "";
    });
    if (!hasValue) {
      return [{ field: fields[0], message: msg || `At least one of ${fields.join(", ")} is required`, code: "at_least_one" }];
    }
    return [];
  };
}

export function when(
  condition: (values: Record<string, unknown>) => boolean,
  fieldName: string,
  validators: FieldValidator[],
): GroupValidator {
  return (values) => {
    if (!condition(values)) return [];
    const errors: ValidationError[] = [];
    for (const v of validators) {
      const err = v(values[fieldName], fieldName);
      if (err) errors.push(err);
    }
    return errors;
  };
}

// ── Schema: Cascading Validation (Tier 3) ─────────────────

export interface ValidationSchema {
  fields?: Record<string, FieldValidator[]>;
  groups?: GroupValidator[];
}

export function validate(schema: ValidationSchema, values: Record<string, unknown>): ValidationResult {
  const fieldErrors: ValidationError[] = [];

  if (schema.fields) {
    for (const [field, validators] of Object.entries(schema.fields)) {
      for (const validator of validators) {
        const err = validator(values[field], field);
        if (err) {
          fieldErrors.push(err);
          break;
        }
      }
    }
  }

  if (fieldErrors.length > 0) {
    return { valid: false, errors: fieldErrors };
  }

  const groupErrors: ValidationError[] = [];
  if (schema.groups) {
    for (const groupValidator of schema.groups) {
      groupErrors.push(...groupValidator(values));
    }
  }

  if (groupErrors.length > 0) {
    return { valid: false, errors: groupErrors };
  }

  return { valid: true, errors: [] };
}

export function validateField(field: string, value: unknown, validators: FieldValidator[]): ValidationError | null {
  for (const v of validators) {
    const err = v(value, field);
    if (err) return err;
  }
  return null;
}

export function getFieldError(result: ValidationResult, field: string): string | undefined {
  return result.errors.find((e) => e.field === field)?.message;
}

// ── Pre-built Schemas ─────────────────────────────────────

export const adminLoginSchema: ValidationSchema = {
  fields: {
    email: [required("Email is required"), email()],
    password: [required("Password is required"), minLength(6, "Password must be at least 6 characters")],
  },
};

export const resetPasswordSchema: ValidationSchema = {
  fields: {
    password: [required("Password is required"), minLength(8, "Password must be at least 8 characters")],
  },
};

export const sendNotificationSchema: ValidationSchema = {
  fields: {
    user_id: [required("User ID is required")],
    message: [required("Message is required"), minLength(1), maxLength(500, "Message too long")],
  },
};

export const createCouponSchema: ValidationSchema = {
  fields: {
    code: [required("Coupon code is required"), pattern(/^[A-Z0-9_-]+$/i, "Invalid coupon code format")],
    discount: [required("Discount is required"), minValue(1, "Minimum discount is 1"), maxValue(100, "Maximum discount is 100")],
  },
};

export const topUpSchema: ValidationSchema = {
  fields: {
    amount: [required("Amount is required"), minValue(1, "Minimum is $1"), maxValue(10000, "Maximum is $10,000")],
  },
};
