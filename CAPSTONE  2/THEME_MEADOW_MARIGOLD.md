# Theme: Meadow & Marigold

Custom design theme for the MSHFI Healthcare system, built from the provided brand palette.
Natural, grounded, and high-contrast — deep forest green anchored by a warm marigold accent.

## Core Palette

| Role                  | Hex       | HSL              | Usage                                            |
|-----------------------|-----------|------------------|--------------------------------------------------|
| Primary — Forest      | `#1F4D11` | 106° 64% 18%     | Buttons, links, focus rings, sidebar active state |
| Secondary — Marigold  | `#F4E23B` | 54° 89% 59%      | Accents, highlights, promo surfaces, charts       |
| Ink — Charcoal        | `#1E1A19` | 12° 9% 11%       | Primary text                                      |
| Danger — Brick        | `#BA1606` | 5° 94% 38%       | Errors, destructive actions, alerts               |
| Surface — Cloud       | `#F7F8F8` | 180° 7% 97%      | App background, muted surfaces                    |

## Derived Scales

### Forest (brand / primary)
50 `#F1F7EC` · 100 `#E0EED5` · 200 `#C3DEAF` · 300 `#9AC67C` · 400 `#5E9A3C`
· **500 `#1F4D11`** · 600 `#183E0C` (hover) · 700 `#12300A` · 800 `#0D2407` · 900 `#081803`

### Marigold (secondary)
50 `#FEFCE9` · 100 `#FBF6C4` · 200 `#F8EE8D` · **300 `#F4E23B`** · 400 `#E6CF19`
· 500 `#C9B412` · 600 `#9C8B0E` · 700 `#6F630C`

### Brick (danger)
50 `#FDF1EE` · 100 `#FBDCD6` · **DEFAULT `#BA1606`** · 600 `#A11305` · 700 `#850F04`

## Typography
Unchanged — Inter for headers and body (existing system font).

## Notes
- White cards float on the Cloud `#F7F8F8` background with a soft forest-green glow shadow
  `rgba(31, 77, 17, …)` replacing the previous teal glow.
- Marigold is used sparingly (soft `#FBF6C4` surfaces, chips, promo gradients) so the
  green stays dominant and text contrast stays accessible.
- Text on Forest 500+ is always white; text on Marigold surfaces uses dark olive/forest.
