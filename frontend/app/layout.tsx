
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
// Your live Vercel production URL from the Meta Sharing Debugger screenshot
const SITE_URL = "https://echofy-eight.vercel.app";
// Unicode Mathematical Sans-Serif Bold Italic so WhatsApp & LinkedIn render
// "𝙀𝙘𝙝𝙤𝙛𝙮 - 𝘼𝙄 𝙙𝙪𝙗𝙗𝙞𝙣𝙜 𝙨𝙩𝙪𝙙𝙞𝙤" in bold italic inside link preview cards
const BOLD_ITALIC_TITLE = "𝙀𝙘𝙝𝙤𝙛𝙮 - 𝘼𝙄 𝙙𝙪𝙗𝙗𝙞𝙣𝙜 𝙨𝙩𝙪𝙙𝙞𝙤";
const DESCRIPTION =
"Upload a video and get it back in Hindi, Telugu, Tamil and more, with a distinct voice for every person on screen.";
// Explicit absolute URL for your OpenGraph image (move your banner image to public/og-image.png or public/logo.png)
const OG_IMAGE_URL = ${SITE_URL}/og-image.png;
export const metadata: Metadata = {
metadataBase: new URL(SITE_URL),
title: BOLD_ITALIC_TITLE,
description: DESCRIPTION,
alternates: {
canonical: SITE_URL,
},
openGraph: {
type: "website",
locale: "en_US",
url: SITE_URL,
siteName: BOLD_ITALIC_TITLE,
title: BOLD_ITALIC_TITLE,
description: DESCRIPTION,
images: [
{
url: OG_IMAGE_URL,
secureUrl: OG_IMAGE_URL,
width: 1200,
height: 630,
alt: "Echofy - AI dubbing studio",
type: "image/png",
},
],
},
twitter: {
card: "summary_large_image",
title: BOLD_ITALIC_TITLE,
description: DESCRIPTION,
images: [OG_IMAGE_URL],
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
<head>
{/* Explicit fallback meta tags for strict scrapers (WhatsApp / Meta Debugger) */}
<meta property="og:image" content={OG_IMAGE_URL} />
<meta property="og:image:secure_url" content={OG_IMAGE_URL} />
<meta property="og:image:type" content="image/png" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
</head>
<body>{children}</body>
</html>
);
}
