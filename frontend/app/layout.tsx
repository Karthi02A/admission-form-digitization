import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Admission Form Digitization",
  description: "Upload, extract, and review admission records.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
