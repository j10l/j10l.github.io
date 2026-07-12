import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Joeran Kinzel | Engineering Leadership & Consulting",
  description:
    "Joeran Kinzel is a software engineering leader and consultant working at the intersection of regulated products, AI, cybersecurity, and organizational scale.",
  icons: {
    icon: "/images/favicon.jpg",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
