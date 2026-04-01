import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function sanitizeText(input: string): string {
  return input.replace(/[<>]/g, '').trim();
}

export function toDateKey(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function isTruthy(value: string | undefined): boolean {
  return value === 'true' || value === '1';
}
