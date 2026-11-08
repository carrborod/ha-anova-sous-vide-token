# Anova Sous Vide (Token)

Start/stop control for Anova Precision Cookers (sous vide) in Home Assistant, using Anova's **official** Wi-Fi API and a personal access token. No account password needed.

It is meant to run alongside Home Assistant's built-in **Anova** integration, which provides the temperature and cook sensors. This one adds control.

## What you get (per cooker)
- **Cook temperature** and **Cook timer** settings
- **Start cook** button (uses those two settings) and **Stop cook** button
- `anova_token.start_cook` action (temperature, unit, minutes) and `anova_token.stop_cook`
- Diagnostics: **API connected**, **API state** (raw state payload as attributes)

## Setup
1. In the Anova Oven app: More > Developer > Personal Access Tokens > create one (starts with `anova-`). Sous vide owners need the Oven app just for this.
2. Install through HACS as a custom repository (type: Integration), restart Home Assistant.
3. Settings > Devices & services > Add integration > **Anova Sous Vide (Token)**, paste the token.

## Notes
- Anova's documented token API covers start, stop and temperature unit only. There is no command to change temperature mid-cook; starting again replaces the current cook.
- Unofficial; not affiliated with Anova Culinary.
