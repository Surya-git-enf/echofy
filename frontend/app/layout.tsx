import type { Metadata, Viewport } from "next";
import { Archivo, Cormorant_Garamond } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";
const archivo = Archivo({
subsets: ["latin"],
variable: "--font-archivo",
display: "swap",
});
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
// Replace with your live frontend domain if hosted on Vercel, or keep Render URL
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://echofy-ty4q.onrender.com";
// Unicode Mathematical Sans-Serif Bold Italic so WhatsApp & LinkedIn render
// the title in genuine bold-italic even inside plain-text link preview cards:
// "𝙀𝙘𝙝𝙤𝙛𝙮 - 𝘼𝙄 𝙙𝙪𝙗𝙗𝙞𝙣𝙜 𝙨𝙩𝙪𝙙𝙞𝙤"
const BOLD_ITALIC_TITLE = "𝙀𝙘𝙝𝙤𝙛𝙮 - 𝘼𝙄 𝙙𝙪𝙗𝙗𝙞𝙣𝙜 𝙨𝙩𝙪𝙙𝙞𝙤";
const DESCRIPTION =
"Upload a video and get it back in Hindi, Telugu, Tamil and more, with a distinct voice for every person on screen while preserving original background music.";
export const metadata: Metadata = {
metadataBase: new URL(SITE_URL),
title: {
default: ${BOLD_ITALIC_TITLE} | Dub Your Video Into Any Language,
template: %s | ${BOLD_ITALIC_TITLE},
},
description: DESCRIPTION,
applicationName: "Echofy - AI dubbing studio",
keywords: [
"Echofy",
"AI dubbing studio",
"Telugu video dubbing",
"Hindi AI dubbing",
"Tamil video translator",
"Fish Audio",
"Demucs vocal separation",
],
authors: [{ name: "Surya" }],
openGraph: {
type: "website",
locale: "en_IN",
url: SITE_URL,
siteName: BOLD_ITALIC_TITLE,
title: BOLD_ITALIC_TITLE,
description: DESCRIPTION,
images: [
{
// Next.js automatically serves app/opengraph-image.png or public/og-image.png
url: "/opengraph-image.png",
width: 1200,
height: 630,
alt: "Echofy - AI dubbing studio preview",
type: "image/png",
},
],
},
twitter: {
card: "summary_large_image",
title: BOLD_ITALIC_TITLE,
description: DESCRIPTION,
images: ["/opengraph-image.png"],
},
icons: {
icon: "/icon.png",
apple: "/icon.png",
},
};
export const viewport: Viewport = { themeColor: "#EEF1F5" };
export default function RootLayout({
children,
}: {
children: React.ReactNode;
}) {
return (
<html
lang="en"
className={${archivo.variable} ${garamond.variable} ${combina.variable}}
>
<body>{children}</body>
</html>
);
}
