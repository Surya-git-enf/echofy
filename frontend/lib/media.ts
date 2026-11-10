// Every asset path in one place. Replace these when the final files are uploaded.
export const FRAME_COUNT = 300;
// Desktop frames are 16:9. For phones, export a vertical (9:16) sequence with the same
// file names to a folder such as "/palace-mobile" and set MOBILE_FRAMES_DIR to it.
export const FRAMES_DIR = "/palace";
export const MOBILE_FRAMES_DIR: string | null = null;
export const frameSrc = (i: number, dir: string = FRAMES_DIR) => `${dir}/palace-frame_${String(i + 1).padStart(4, "0")}.webp`;

// Language Vibes card. Rename to /videos/dubbed.mp4 once that file is uploaded.
export const LANGUAGE_VIDEO = "/videos/echofy_captioned.mp4";

// Showcase orbit: 5 vertical (9:16) dubbed videos. Until Dubbed1..5.mp4 are uploaded
// every slot plays the one video that exists.
export const SHOWCASE_VIDEOS = [1, 2, 3, 4, 5].map((n) => ({
  id: n,
  src: "/videos/echofy_captioned.mp4", // later: `/videos/Dubbed${n}.mp4`
  label: `Dubbed ${n}`,
}));

// Small images the page loader waits for besides the hero frames.
export const PRELOAD_IMAGES = ["/logo.png", "/cards/card1.png", "/cards/card3.png", "/scratch/cover.webp", "/scratch/won.webp"];

export const INSTAGRAM_URL = "https://www.instagram.com/itz_surya.13?mdxt=MWp0YzZ6cTJyMTJ0aQ==";
export const DISCORD_HANDLE = "ayrus0101";
