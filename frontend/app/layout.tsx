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

const siteTitle = "𝙀𝙘𝙝𝙤𝙛𝙮 - 𝘼𝙄 𝙙𝙪𝙗𝙗𝙞𝙣𝙜 𝙨𝙩𝙪𝙙𝙞𝙤";
const siteDescription = "Upload a video and get it back in Hindi, Telugu, Tamil and more, with a distinct voice for every person on screen.";
// 1200x630 copy of og-image.png, small enough (about 100 KB) for WhatsApp and other apps that skip big previews.
// The query string makes apps fetch it fresh instead of reusing the old logo preview.
const siteImageUrl = "https://echofy-eight.vercel.app/og-share.jpg?v=2";

export const metadata: Metadata = {
  metadataBase: new URL("https://echofy-eight.vercel.app"),
  title: siteTitle,
  description: siteDescription,
  icons: { icon: "/logo.png", apple: "/logo.png" },
  openGraph: {
    title: siteTitle,
    siteName: siteTitle,
    description: siteDescription,
    type: "website",
    locale: "en_US",
    url: "https://echofy-eight.vercel.app",
    images: [
      {
        url: siteImageUrl,
        width: 1200,
        height: 630,
        type: "image/jpeg",
        alt: "Echofy - AI dubbing studio",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: siteTitle,
    description: siteDescription,
    images: [
      {
        url: siteImageUrl,
        width: 1200,
        height: 630,
        type: "image/jpeg",
        alt: "Echofy - AI dubbing studio",
      },
    ],
  },
};

export const viewport: Viewport = { themeColor: "#EEF1F5" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={[archivo.variable, garamond.variable, combina.variable].join(" ")}>
      <body>{children}</body>
    </html>
  );
}