import { z } from "zod";

const envSchema = z.object({
  SPORTS_ANALYTICS_BACKEND_URL: z.string().url().optional(),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
  const flattened = parsed.error.flatten().fieldErrors;
  throw new Error(`Invalid environment variables: ${JSON.stringify(flattened)}`);
}

export const env = parsed.data;
