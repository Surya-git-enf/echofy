import type { Metadata, Viewport } from "next";
import { Archivo, Cormorant_Garamond } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

const archivo = Archivo({ subsets: ["latin"], variable: "--font-archivo", display: "swap" });
const garamond = Cormorant_Garamond({
  subsets: ["latin"],
  weight: ["300"],
  style: ["italic", "normal"],
  variable: "--font-garamond",
  display: "swap",
});
const combina = localFont({
  src: "../public/fonts/Combina-Trial-Regular.otf",
  variable: "--font-combina",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Echofy: dub your video into any language",
  description: "Upload a video and get it back in Hindi, Telugu, Tamil and more, with a distinct voice for every person on screen.",
};

export const viewport: Viewport = { themeColor: "#EEF1F5" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${archivo.variable} ${garamond.variable} ${combina.variable}`}>
      <body>{children}</body>
    </html>
  );
}
