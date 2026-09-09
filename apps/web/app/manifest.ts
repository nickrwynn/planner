import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "StudyFlows",
    short_name: "StudyFlows",
    description: "StudyFlows — courses, resources, and study tools",
    start_url: "/",
    display: "standalone",
    background_color: "#fafafa",
    theme_color: "#111827",
    orientation: "any",
    icons: [
      {
        src: "/icon?size=192",
        sizes: "192x192",
        type: "image/png"
      },
      {
        src: "/icon?size=512",
        sizes: "512x512",
        type: "image/png"
      },
      {
        src: "/apple-icon",
        sizes: "180x180",
        type: "image/png"
      }
    ]
  };
}
