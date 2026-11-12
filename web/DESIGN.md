# go2china.space design direction

Read this before changing the page. It exists so the site keeps looking like a real travel product, not a template.

## Subject

Foreign travellers in mainland China. The page sells one thing: a personal agent in your pocket (CJ Agent) with a team behind it (JT Agent and real people). Everything on the page should be about travelling in China; if a sentence would fit any other app's site, rewrite it.

References that informed this direction: Mindtrip (real photography, big plain headlines, solid colour story panels), Flighty (the product's real UI as the hero), Layla and Wanderlog (one clear call to action).

## Palette

| Token | Hex | Use |
|---|---|---|
| Paper | `#FFFFFF` | Page background |
| Stone | `#F3F2EF` | Alternate section background, form fields |
| Ink | `#1D1D1B` | Text, dark buttons |
| Muted | `#62605B` | Secondary text |
| Cinnabar | `#C41E24` | The CTA, CJ Agent, from the mascot's red |
| Jade | `#0D6450` | JT Agent and the human team, from the mascot's jade |
| Porcelain | `#1F3A68` | The privacy panel, after blue-and-white porcelain |
| Gold | `#E0B04E` | Small highlights on dark panels only |

Solid colours only: no gradients, glows, glass or blur.

## Type

- One family: **Onest** (self-hosted, Latin and Cyrillic, 400/500/600/700). Arabic uses **IBM Plex Sans Arabic**; Chinese uses the system font (PingFang SC, Microsoft YaHei, Noto Sans CJK).
- Headlines are bold and tight (letter-spacing about -0.025em); no italics, no coloured or italic accent word.
- Body 18px with 1.55 line height, lines under about 70 characters.
- Sentence case everywhere. No all-caps labels, no eyebrows above headings, no 01/02/03 markers.

## Layout and components

- The hero is a real photograph of China with the product (the phone chat) on top of it.
- Story panels are flat colour blocks with a 28px radius; photos 18px; inputs 12px; buttons are pills.
- Tabular facts go in real tables or rows, not identical cards.
- No icon tiles, no pill badges above headlines, no feature-card grids.

## Motion

- Two demos move on their own because they show the product: the chat (typing, deleting, sending) and the redaction. The photo wall swaps one photo at a time.
- Everything else moves only when the user does something (switching a scenario tab, submitting the form).
- No fade-up on scroll. Respect `prefers-reduced-motion`: show final states, stop the photo swaps.

## China access

- No third-party requests from the browser: fonts, images and scripts are served from go2china.space.
- The early access form posts to `/api/early-access` on the same domain; the server forwards it to Jotform.
