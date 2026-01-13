import type { Metadata } from "next";
import { DM_Mono, Sora } from "next/font/google";
import "./globals.css";
import NavBar from "../components/NavBar";

const sora = Sora({
  variable: "--font-sora",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const dmMono = DM_Mono({
  variable: "--font-dm-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "SupportOps",
  description: "Agent-assisted helpdesk runtime",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${sora.variable} ${dmMono.variable} antialiased`}>
        <NavBar />
        {children}
      </body>
    </html>
  );
}
