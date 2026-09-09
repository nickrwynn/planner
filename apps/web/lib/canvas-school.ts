/** Guess Canvas base URL from a school email (extend as needed). */
export function canvasBaseUrlFromEmail(email: string): string {
  const domain = email.trim().toLowerCase().split("@")[1] || "";
  if (domain === "tamu.edu" || domain.endsWith(".tamu.edu")) {
    return "https://canvas.tamu.edu";
  }
  // Default for this product’s primary school; user can edit the field.
  return "https://canvas.tamu.edu";
}

export const CONNECT_CANVAS_FLAG = "aos_connect_canvas";
export const CONNECT_CANVAS_EMAIL = "aos_connect_canvas_email";
