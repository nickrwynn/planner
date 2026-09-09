"use client";

import { useEffect } from "react";
import { applyTheme, getStoredTheme } from "../lib/theme";

export function ThemeBoot() {
  useEffect(() => {
    applyTheme(getStoredTheme());
  }, []);
  return null;
}
