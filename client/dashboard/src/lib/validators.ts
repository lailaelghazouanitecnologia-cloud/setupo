// ══════════════════════════════════════════════════════════════
//  NSO Validation System — Cascading Field → Group → Form
// ══════════════════════════════════════════════════════════════
//
//  Three tiers:
//    1. Field validators  — single value checks (required, minLen, email, etc.)
//    2. Group validators  — cross-field checks (passwordMatch, dateRange, etc.)
//    3. Form validation   — cascades field → group, short-circuits on first tier failure
//

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

/** Validates env var key format: UPPER_SNAKE_CASE */
export function envKey(msg?: string): FieldValidator {
  return pattern(/^[A-Z][A-Z0-9_]*$/, msg || "Must be UPPER_SNAKE_CASE (e.g. MY_VAR)");
}

/** Validates slug format: lowercase, alphanumeric, hyphens */
export function slug(msg?: string): FieldValidator {
  return pattern(/^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$/, msg || "Must be lowercase with hyphens (e.g. my-project)");
}

/** Validates domain format */
export function domain(msg?: string): FieldValidator {
  return pattern(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/, msg || "Invalid domain format");
}

// ── Group Validators (Tier 2) ─────────────────────────────

/** Check that two fields match (e.g. password confirmation) */
export function fieldsMatch(fieldA: string, fieldB: string, msg?: string): GroupValidator {
  return (values) => {
    if (values[fieldA] !== values[fieldB]) {
      return [{ field: fieldB, message: msg || `${fieldB} must match ${fieldA}`, code: "fields_match" }];
    }
    return [];
  };
}

/** Check that field A < field B numerically */
export function fieldLessThan(fieldA: string, fieldB: string, msg?: string): GroupValidator {
  return (values) => {
    const a = Number(values[fieldA]);
    const b = Number(values[fieldB]);
    if (!isNaN(a) && !isNaN(b) && a >= b) {
      return [{ field: fieldA, message: msg || `${fieldA} must be less than ${fieldB}`, code: "field_less_than" }];
    }
    return [];
  };
}

/** At least one of the given fields must be filled */
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

/** Conditional: run validators on a field only when a condition is met */
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
  /** Field-level validators: run first, per-field */
  fields?: Record<string, FieldValidator[]>;
  /** Group-level validators: run second, only if all field validations pass */
  groups?: GroupValidator[];
}

/**
 * Validate values against a schema using cascading tiers:
 *   Tier 1: field validators → if ANY fail, return errors (skip groups)
 *   Tier 2: group validators → cross-field checks
 *
 * This ensures simple errors are caught first before running
 * more expensive cross-field validation.
 */
export function validate(schema: ValidationSchema, values: Record<string, unknown>): ValidationResult {
  const fieldErrors: ValidationError[] = [];

  // ── Tier 1: Field validators ──
  if (schema.fields) {
    for (const [field, validators] of Object.entries(schema.fields)) {
      for (const validator of validators) {
        const err = validator(values[field], field);
        if (err) {
          fieldErrors.push(err);
          break; // stop at first error per field
        }
      }
    }
  }

  // Short-circuit: if field errors exist, don't run groups
  if (fieldErrors.length > 0) {
    return { valid: false, errors: fieldErrors };
  }

  // ── Tier 2: Group validators ──
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

/**
 * Validate a single field against its validators.
 * Useful for real-time inline validation on blur/change.
 */
export function validateField(field: string, value: unknown, validators: FieldValidator[]): ValidationError | null {
  for (const v of validators) {
    const err = v(value, field);
    if (err) return err;
  }
  return null;
}

/**
 * Get the first error message for a specific field from a ValidationResult.
 */
export function getFieldError(result: ValidationResult, field: string): string | undefined {
  return result.errors.find((e) => e.field === field)?.message;
}

// ── Pre-built Schemas ─────────────────────────────────────

export const loginSchema: ValidationSchema = {
  fields: {
    email: [required("Email is required"), email()],
    password: [required("Password is required"), minLength(6, "Password must be at least 6 characters")],
  },
};

export const registerSchema: ValidationSchema = {
  fields: {
    email: [required("Email is required"), email()],
    password: [required("Password is required"), minLength(6, "Password must be at least 6 characters")],
    name: [maxLength(100, "Name is too long")],
  },
};

export const createProjectSchema: ValidationSchema = {
  fields: {
    name: [required("Project name is required"), minLength(2, "Name must be at least 2 characters"), maxLength(64, "Name is too long")],
  },
};

export const addSecretSchema: ValidationSchema = {
  fields: {
    key: [required("Key is required"), envKey()],
    value: [required("Value is required")],
  },
};

export const createWorkspaceSchema: ValidationSchema = {
  fields: {
    name: [required("Name is required"), slug("Name must be lowercase with hyphens"), maxLength(64)],
  },
};

export const topUpSchema: ValidationSchema = {
  fields: {
    amount: [required("Amount is required"), minValue(5, "Minimum top-up is $5"), maxValue(1000, "Maximum top-up is $1,000")],
  },
};

export const addDomainSchema: ValidationSchema = {
  fields: {
    domain: [required("Domain is required"), domain()],
  },
};

export const couponSchema: ValidationSchema = {
  fields: {
    code: [required("Coupon code is required"), pattern(/^[A-Z0-9_-]+$/i, "Invalid coupon code format")],
  },
};
