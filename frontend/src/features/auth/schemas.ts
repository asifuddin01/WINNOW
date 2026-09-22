import { z } from "zod";

export const MIN_PASSWORD = 12;

export const email = z.email("Enter a valid email address.").max(254);
export const existingPassword = z.string().min(1, "Enter your password.").max(256);
export const newPassword = z
  .string()
  .min(MIN_PASSWORD, `Use at least ${MIN_PASSWORD} characters.`)
  .max(256, "Use at most 256 characters.");
export const name = z.string().trim().min(1, "Enter your name.").max(200);

export const PASSWORD_HINT = `At least ${MIN_PASSWORD} characters. A few unrelated words make a strong, memorable password.`;

export const signInSchema = z.object({
  email,
  password: existingPassword,
  code: z.string().max(32),
});
export const registerSchema = z.object({ name, email, password: newPassword });
export const emailSchema = z.object({ email });
export const resetSchema = z.object({ password: newPassword });
export const changePasswordSchema = z.object({ current: existingPassword, next: newPassword });

export type SignInValues = z.infer<typeof signInSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type EmailValues = z.infer<typeof emailSchema>;
export type ResetValues = z.infer<typeof resetSchema>;
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
